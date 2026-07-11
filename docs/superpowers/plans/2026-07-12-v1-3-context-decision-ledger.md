# AET v1.3 Context Manifest and Decision Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Release v1.3.0 with deterministic local context provenance and source-backed project decisions, without adding an Agent runtime, retrieval system, or opaque trust score.

**Architecture:** Add two small, independent JSON artifacts. `context_manifest` snapshots discovered instructions/Skills and explicitly labels a read declaration as an attestation; `decision_ledger` stores local source hashes and a supersession chain. Both validate only local filesystem and Git state using the standard library.

**Tech Stack:** Python 3.11 standard library, `argparse`, JSON, SHA-256, `unittest`, uv, GitHub Actions.

---

## Scope and invariants

- `context discover` proves only discovery and file hashes. `context record --read` stores an `agent_attestation`; it never proves a model read, understood, or used content.
- `context verify` and `decision verify` are read-only and return non-zero for changed/missing sources. They do not rewrite a successful proof or finding.
- Ledger sources are existing regular files inside the manifest's repository root. Remote data, embeddings, RAG, model calls, background writes, and generic command execution remain out of scope.
- JSON is deliberately used instead of YAML so creation and validation need no dependency or permissive parser.

## File map

- Create: `src/aet/context.py` — Context Manifest data creation, attestation recording, and freshness verification.
- Create: `src/aet/decision.py` — Decision Ledger creation, add/list/verify/supersede operations and source-hash validation.
- Modify: `src/aet/cli.py` — `context` and `decision` command routing with unambiguous exit codes.
- Modify: `tests/test_productization.py` — clean and failing lifecycle coverage for each artifact.
- Modify: `README.md`, `docs/README.zh-CN.md`, `skills/agent-engineering-toolkit/SKILL.md` — user contract, examples, and boundary.
- Modify: `CHANGELOG.md`, `PROJECT_MEMORY.md`, `docs/productization-plan.md` — release record and design rationale.
- Modify: `pyproject.toml`, `src/aet/__init__.py`, `uv.lock`, `.github/workflows/ci.yml` — v1.3.0 distribution metadata and isolated wheel smoke target.

### Task 1: Establish the v1.3 release contract

**Files:**
- Modify: `aet.intent.json`
- Modify: `docs/superpowers/plans/2026-07-12-v1-3-context-decision-ledger.md`

- [ ] **Step 1: Replace the previous release intent**

Set the intent to permit `src/aet/**`, `tests/**`, docs, the portable Skill, packaging metadata, and GitHub workflow changes. Require the full regression suite as the bound proof, with `src/aet/context.py`, `src/aet/decision.py`, and `tests/test_productization.py` as evidence paths.

- [ ] **Step 2: Review the eventual diff against `main`**

Run: `uv run --no-editable aet review . --base main --intent aet.intent.json --format json --output /tmp/aet-v13-review.json`

Expected: the review reports all changed paths inside the v1.3 scope; it does not execute a command.

### Task 2: Add Context Manifest behavior test-first

**Files:**
- Create: `src/aet/context.py`
- Modify: `src/aet/cli.py`
- Test: `tests/test_productization.py`

- [ ] **Step 1: Write a clean-and-stale regression test**

Create a temporary Git root containing `AGENTS.md`, `skills/example/SKILL.md`, `docs/architecture.md`, and `.gitignore` for `.aet/`. The test must run:

```python
main(["context", "discover", ".", "--output", str(manifest)])
main(["context", "record", "--manifest", str(manifest), "--read", "AGENTS.md", "--reference", "docs/architecture.md"])
main(["context", "verify", "--manifest", str(manifest), "--format", "json"])
```

Assert that `AGENTS.md` is `declared_read` with `declaration_source == "agent_attestation"`, the reference is present with role `reference`, the first verification is `PASS`, and editing `AGENTS.md` makes a second verification return `1` with an asset `FAIL`.

- [ ] **Step 2: Implement the minimal artifact contract**

`context_discover(root, output, config)` writes non-overwriting JSON with `report_kind: "context_manifest"`, root, generated time, workspace snapshot, and `{path, role, sha256, discovered, declared_read}` assets. `context_record` accepts only root-relative regular files, updates existing asset declarations, and adds `--reference` files with `role: "reference"`. `context_verify` compares saved hashes and `compare_workspace_snapshots`, returning a portable `context_verification` result.

- [ ] **Step 3: Route the CLI and verify the focused test**

Run: `uv run --no-editable python -m unittest tests.test_productization.ProductizationTests.test_context_manifest_distinguishes_discovery_attestation_and_drift -v`

Expected: PASS.

### Task 3: Add Decision Ledger behavior test-first

**Files:**
- Create: `src/aet/decision.py`
- Modify: `src/aet/cli.py`
- Test: `tests/test_productization.py`

- [ ] **Step 1: Write a source and supersession regression test**

In a temporary Git root with `docs/decision-source.md`, initialize `.aet/decisions.json`, add `DEC-0001` as `EVIDENCED`/`ACCEPTED` with that source, then add `DEC-0002` that supersedes it. Assert list output marks the first decision `SUPERSEDED`, verifies unchanged sources as `PASS`, then changes the source and verifies `FAIL`.

- [ ] **Step 2: Implement the ledger contract**

`decision_init` writes a non-overwriting ledger. `decision_add` rejects duplicate IDs, outside-root/non-file sources, unsupported evidence states, and nonexistent superseded IDs. It stores each source's root-relative path and SHA-256. `decision_supersede` requires an accepted replacement decision and records a timestamped event. `decision_verify` compares every source hash and returns only observed states; it does not alter ledger history.

- [ ] **Step 3: Verify the focused test**

Run: `uv run --no-editable python -m unittest tests.test_productization.ProductizationTests.test_decision_ledger_tracks_evidence_and_supersession -v`

Expected: PASS.

### Task 4: Make the public contract release-ready

**Files:**
- Modify: `README.md`
- Modify: `docs/README.zh-CN.md`
- Modify: `skills/agent-engineering-toolkit/SKILL.md`
- Modify: `CHANGELOG.md`
- Modify: `PROJECT_MEMORY.md`
- Modify: `docs/productization-plan.md`
- Modify: `pyproject.toml`
- Modify: `src/aet/__init__.py`
- Modify: `uv.lock`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Document commands and epistemic boundary**

Add capability-table rows and a compact copyable flow for `context discover/record/verify` and `decision init/add/list/verify/supersede`. State that a declared read is an L5 attestation, while discovered/local-hash facts are L1; neither is evidence of model understanding. State that Decision Ledger is source-backed project memory, not generic Agent memory/RAG.

- [ ] **Step 2: Update package and CI versions**

Set all version references to `1.3.0`, regenerate the lockfile with `uv lock`, and point CI's isolated wheel smoke command at `dist/agent_engineering_toolkit-1.3.0-py3-none-any.whl`.

- [ ] **Step 3: Add a dated changelog entry**

Describe only the shipped behavior: deterministic Context Manifest, attestation semantics, JSON Decision Ledger, source verification/supersession, tests, and docs. Do not claim remote retrieval, semantic understanding, or autonomous memory.

### Task 5: Verify, pack, publish, and record the release

**Files:**
- Modify: repository release files only when verification identifies a real defect.

- [ ] **Step 1: Run static and regression gates**

Run:

```bash
uv run --no-editable --reinstall-package agent-engineering-toolkit python -m unittest discover -s tests -v
uv run --no-editable aet audit . --strict --format json --output /tmp/aet-v13-audit.json
uv run --no-editable aet review . --base main --intent aet.intent.json --format json --output /tmp/aet-v13-review.json
```

Expected: full suite, strict audit, and scoped review pass.

- [ ] **Step 2: Build and smoke-test the actual wheel through Trace**

Run `uv build`; then use `aet trace --proof regression-suite` for the declared regression command and compile an Evidence Pack with the audit, review, and trace. Separately install the generated wheel with `uv run --isolated --with dist/agent_engineering_toolkit-1.3.0-py3-none-any.whl aet --version` and require `1.3.0`.

- [ ] **Step 3: Commit, tag, push, and verify the release**

Commit only the reviewed v1.3 files, create annotated tag `v1.3.0`, push `main` and the tag to `origin`, then check the GitHub Release workflow result and release URL. Update `PROJECT_MEMORY.md` with actual command outcomes, commit SHA, tag, and release URL only after they exist.

## Self-review

- Spec coverage: Context Manifest, declared-read boundary, Decision Ledger, evidence verification, supersession, tests, docs, versioning, release, and Evidence Pack are each assigned above.
- Deliberate omissions: no RAG/vector database, model telemetry, host adapter, runtime scheduling, synthetic score, or non-local source handler; each would exceed the v1.3 boundary.
- Type consistency: CLI names are `context discover|record|verify` and `decision init|add|list|verify|supersede`; artifact names are `context_manifest`, `context_verification`, and `decision_ledger`.
