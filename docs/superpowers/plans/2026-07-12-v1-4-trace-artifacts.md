# Trace Artifact Capture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use task-by-task execution with tests before implementation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let `aet trace` carry an explicitly declared text report produced by a command (for example pytest JUnit XML) into the Trace and portable Evidence Pack, while preserving redaction and honest `UNKNOWN` states.

**Architecture:** Keep command execution unchanged: Trace still runs only argv after `--`. Add a repeatable `--artifact PATH` declaration; after the child exits, AET validates each path is a regular file beneath the workspace, UTF-8 decodes and redacts its content, then records its exact redacted bytes and SHA-256. The Evidence Pack embeds only these explicitly requested redacted artifacts, so test reports are portable without collecting arbitrary files.

**Tech Stack:** Python 3.11+ standard library (`argparse`, `pathlib`, `hashlib`, `subprocess`, `json`); no new dependency.

---

## Scope and invariants

- This addresses the Invest-Vault observation accurately: Trace successfully ran `uv run --with pytest pytest -q` (exit 0), but its v1.3 record had only stdout/stderr and no pytest report artifact.
- AET does not infer output paths from pytest or any other tool. Every capture is user-declared with `--artifact`.
- Capture is limited to regular files inside the Trace working directory. Missing, directory, outside-root, undecodable, or unredactable artifacts become `UNKNOWN`; they never become a fabricated PASS.
- The child process's exit code remains distinct from artifact-capture completeness. A successful command with a missing declared artifact exits AET non-zero to make CI fail closed.
- Raw stdout/stderr remain excerpt-and-digest only. Only an explicitly requested, redacted text artifact may be embedded in a portable Evidence Pack.
- Do not add an agent runtime, automatic retries, report-format parser, RAG/memory system, or a dependency.

## File map

- Modify: `src/aet/evidence.py` — capture and portable serialization of declared artifacts.
- Modify: `src/aet/cli.py` — repeatable `trace --artifact` argument and capture-aware result.
- Modify: `tests/test_audit.py` — clean, missing, outside-root, and Evidence Pack regression coverage.
- Modify: `README.md`, `docs/README.zh-CN.md`, `docs/security-and-retention.md` — command, privacy, and evidence-boundary documentation.
- Modify: `CHANGELOG.md`, `pyproject.toml`, `src/aet/__init__.py`, `uv.lock`, `.github/workflows/ci.yml`, `skills/agent-engineering-toolkit/SKILL.md`, `PROJECT_MEMORY.md` — v1.4 release metadata and Skill contract.

### Task 1: Lock the capture contract with failing tests

**Files:**
- Modify: `tests/test_audit.py`

- [ ] Add a test which runs a child Python process that writes `reports/junit.xml` containing a secret, calls `aet trace --artifact reports/junit.xml`, and asserts: child execution is PASS, artifact status is PASS, the full stored report is redacted, its SHA-256 matches the stored redacted content, and the original secret is absent from `trace.json`.
- [ ] Compile an Evidence Pack from that Trace and assert the portable trace includes the artifact's requested path, digest, and redacted content.
- [ ] Add a test for a successful child with a missing declared artifact; assert Trace exits 1, records `UNKNOWN`, and keeps `execution.exit_code == 0`.
- [ ] Add a test for a declared absolute artifact outside the workspace; assert the CLI rejects it before command execution.
- [ ] Run: `uv run --no-editable python -m unittest tests.test_audit.AuditTests.test_trace_captures_declared_report_artifact -v`.

### Task 2: Implement the smallest safe capture path

**Files:**
- Modify: `src/aet/evidence.py`
- Modify: `src/aet/cli.py`

- [ ] Add `--artifact`, `action="append"`, to the Trace parser and pass the values to `trace_command`.
- [ ] Add a path resolver that rejects an absolute path or a resolved target outside `cwd`; this validates declarations before launching the command.
- [ ] After the child completes, read each declared regular file; reuse the existing UTF-8/redaction path; record `{requested_path, status, sha256, content}`. For a missing/non-regular/undecodable/unredactable target, record an `UNKNOWN` item with a reason and no content.
- [ ] Add the artifact count to Trace's `UNKNOWN` summary. Return the child exit code when non-zero; otherwise return 1 if any requested artifact is not PASS, else 0.
- [ ] Extend `_portable_report` to copy only declared artifact fields, including full redacted content; keep stdout/stderr excerpt-only.
- [ ] Run the tests from Task 1 to green.

### Task 3: Document the boundary and release v1.4.0

**Files:**
- Modify: documentation and metadata files listed above.

- [ ] Document this exact flow:

```bash
aet trace --artifact reports/junit.xml --output .aet/evidence/pytest-trace.json -- \
  pytest --junitxml=reports/junit.xml
aet evidence pack --trace .aet/evidence/pytest-trace.json --output .aet/evidence/evidence-pack.json
```

- [ ] State that an artifact is captured only when explicitly requested, must be UTF-8 text under the workspace, is redacted before persistence, and is included in a Pack only because the user explicitly requested it.
- [ ] Update all versioned metadata and release links to `1.4.0`; add a concise changelog entry naming the Invest-Vault-derived regression.

### Task 4: Verify with a real pytest subprocess and ship

- [ ] Run the full test suite and strict self-audit.
- [ ] In a disposable Git fixture, use the real `pytest --junitxml` subprocess through `aet trace --artifact`, compile a pack, and validate the report is embedded, redacted, and hash-consistent.
- [ ] Build the wheel and invoke it in an isolated environment.
- [ ] Produce release audit/review/trace/Evidence Pack after commit; require proof and snapshot bindings to PASS.
- [ ] Commit, tag `v1.4.0`, push `main` and tag, then confirm both CI and the release workflow and inspect the public release asset.

## Self-review

- Spec coverage: explicit pytest report capture, portable pack inclusion, truthful missing-artifact handling, Harness-document-derived filesystem artifacts and failure visibility, README/changelog, regression/self-tests, and release all map to a task.
- No placeholders: every command and changed responsibility is explicit.
- Type consistency: the public term is `--artifact`; report data is `trace.artifacts`; artifact state uses the existing `PASS`/`UNKNOWN` vocabulary.
