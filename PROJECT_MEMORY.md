# Agent Engineering Toolkit — Project Memory

## Canonical workspace

All future implementation work belongs in:
`/Users/yjw/agent/Agent Engineering Toolkit`

This repository was migrated here on 2026-07-11 with its Git history, phase
tags, local fixtures, and dogfood snapshots intact. Treat this path as the only
active workspace; the prior Codex-generated directory is archival.

## Resume protocol

At the start of any new task, read this file, then run `git status --short`,
`git tag --sort=-creatordate | head`, and
`uv run --no-editable python -m unittest discover -s tests`. Do not start a
later phase until the current phase's acceptance checks pass and this file is
updated.

## Product decision

`aet` is an Evidence First, read-only engineering gate for coding-agent
context and Skills. It proves what can be inspected locally and reports
unknowns; it never invents a holistic trust score.

Primary users are individual developers and small teams using Codex, Claude
Code, Cursor, Copilot, or compatible agent Skills across multiple repositories.

The final distributable form is the canonical cross-agent Skill in
`skills/agent-engineering-toolkit/`; the `aet` CLI is its deterministic local
runtime. Every shipped capability must be exposed through this tool-neutral
Skill and retain JSON/SARIF evidence contracts so any agent host can invoke it.

Out of scope: an agent runtime, a Skill marketplace, automatic prompt rewrites,
and model-dependent prompt regression. The only retained later expansion is
**Repo Archaeologist**, planned as `aet evolve`, not a dependency of the static
core.

## Non-negotiable design rules

1. Local, deterministic, and read-only by default; no LLM or API key in v0.1.
2. Every finding has a stable ID, status, severity, evidence location,
   remediation, and rule version.
3. Use `PASS`, `FAIL`, `UNKNOWN`, and `NOT_APPLICABLE`; do not produce a single
   opaque score.
4. Keep the core dependency-light. Python 3.11+ standard library is sufficient
   for v0.1.
5. New rules require a fixture that proves both a clean and failing case.
6. End every phase by: testing, committing, tagging, updating this file, and
   bumping/installing the local Skill version.

## Architecture

`discovery.py` locates context assets → `rules.py` produces evidence-backed
findings → `reporters.py` serializes Markdown, JSON, or SARIF → `cli.py`
controls output and CI exit status.

Supported v0.1 assets: `AGENTS.md`, `CLAUDE.md`, `CODEX.md`,
`copilot-instructions.md`, `.cursorrules`, and every `SKILL.md` below the
target root.

## Version and rollback ledger

| Stage | Version | Git tag | Result | Rollback |
|---|---:|---|---|---|
| Phase 0 | Skill 0.0.1 | `phase-0-dogfood` | Workspace, fixtures, dogfood baseline, project memory, and conservative path semantics. | `git checkout phase-0-dogfood` |
| v0.1 | Skill 0.1.0 / package 0.1.0 | `v0.1.0` | Static context and Skill audit CLI with Markdown, JSON, SARIF, CI example, tests, and wheel verification. | `git checkout v0.1.0` |
| v0.2 | Skill 0.2.0 / package 0.2.0 | `v0.2.0` | Intent Gate: human-reviewable contract, changed-path budget, scope checks, and proof-evidence checks. | `git checkout v0.2.0` |
| Skill portability | Skill 0.2.1 / package 0.2.0 | `skill-v0.2.1` | Tool-neutral `SKILL.md` cleanup and cross-agent contract. | `git checkout skill-v0.2.1` |
| v0.3 | Skill/package 0.3.0 | `v0.3.0` | Host-neutral Evidence Pack compiler and opt-in, redacted command Trace. | `git checkout v0.3.0` |

## Current implementation status

v0.3 complete. The deterministic static core now includes host-neutral
Evidence Packs and explicit command Trace. Repo Archaeologist remains a
separate future `aet evolve` capability.

### Phase 0 result — 2026-07-11

- Initialized this repository and the `agent-engineering-toolkit` Skill.
- Added clean and broken fixtures plus an initial evidence schema and static
  rule prototype for dogfooding.
- Audited read-only shallow clones stored outside Git tracking:
  - `stock-analysis` at `e875974992e8a5258df9723ead115390efecf5a1`
  - `pain-miner` at `ddf3ce20a1bc0cfbd04b79ac76c8e713b6ff0fda`
  - `cli-creator-skill` at `418e941607a53be95921edbbb8e2196411b7893d`
- Final dogfood reports are in `docs/dogfood/`; each discovered one Skill and
  emitted zero FAIL/UNKNOWN findings under the v0.1 prototype.
- Dogfood corrected two false-positive risks before release: generated output
  names are not local paths, and verification detection recognises Chinese as
  well as English wording.
- Local Skill installed at
  `~/.codex/skills/agent-engineering-toolkit`, version `0.0.1`.

### v0.1 result — 2026-07-11

- Released the read-only `aet audit [path]` command with Markdown, JSON, and
  SARIF output plus CI exit semantics (`FAIL` always fails; `--strict` also
  fails on `WARN`).
- Implemented deterministic checks for missing local Markdown/explicit command
  targets, root instruction bloat, duplicate long directives, required Skill
  frontmatter, Skill name/directory mismatch, and verification instructions.
- Added four standard-library tests covering clean and failing fixtures, CLI
  exit codes, and SARIF parsing. Use the exact resume command above.
- Added a GitHub Actions SARIF example and built a source distribution and
  wheel. Release verification includes running the wheel from a fresh temporary
  virtual environment.
- Upgraded and reinstalled the local Skill at
  `~/.codex/skills/agent-engineering-toolkit`, version `0.1.0`.
- On this Python 3.13 + uv environment, editable installs create an
  underscore-prefixed `.pth` file that CPython skips. Use `uv run
  --no-editable` for local verification; released wheels are unaffected.

### v0.2 result — 2026-07-11

- Added `aet review --base <revision>`, which reads a human-authored
  `aet.intent.json`, compares the working tree (including untracked files) to
  the Git base, and emits evidence-backed `AET-REV-001` through
  `AET-REV-004` findings for contract validity, changed-path budget, scope,
  and local proof evidence.
- Intent Gate stays read-only: it never executes declared proof commands. A
  PASS for proof evidence means the command and local evidence were declared;
  human review must run the command separately before claiming it passed.
- Added passing and failing Git-backed review tests, then verified the 0.2.0
  wheel in a fresh virtual environment. The local Skill is updated to 0.2.0
  with the v0.2 contract reference.

### Skill portability result — 2026-07-11

- Removed the generated-template residue from the canonical Skill and made its
  workflow tool-neutral: the shared boundary is `aet` plus JSON/SARIF output,
  not any vendor-specific API.
- Added `references/cross-agent-use.md`. Native Skill hosts install the whole
  folder; agents without native Skill support can load `SKILL.md` as project
  instructions and invoke the same CLI.
- `agents/openai.yaml` remains optional UI metadata. It must never become a
  runtime dependency or reduce compatibility for another agent host.
- Upgraded and reinstalled the local Skill to `0.2.1` after structural
  validation and the current test suite passed.

## v0.3 result — 2026-07-11

- Added `aet trace --output ... -- <command> [args...]`: the sole opt-in
  execution path. It records redacted argv, exit status, timestamps, working
  directory, Git HEAD/worktree digest, and SHA-256 digests of redacted
  stdout/stderr artifacts. A non-zero command produces a valid `FAIL` Trace;
  it is not successful proof.
- Added `aet evidence pack`, which schema-validates independently produced
  audit, review, and trace JSON, records source SHA-256 values, atomically
  writes a portable JSON pack, and marks missing optional components
  `UNKNOWN`. It preserves component summaries and excludes raw command logs.
- Added acceptance coverage for successful and failing commands, built-in
  secret redaction, stable hashes, invalid schemas, missing inputs, atomic
  replacement, and an audit → review → trace → pack temporary Git fixture.
- Ran 11 unit tests through Trace, built 0.3.0 source/wheel distributions, and
  installed the wheel into a fresh virtual environment for a Trace smoke test.
- Updated the canonical and local cross-agent Skill to 0.3.0 with the portable
  `v0.3-contract.md` reference.

## Released phase: v0.3 Evidence Pack and Trace

### Objective (completed)

Turn the existing audit and review reports plus explicitly requested command
execution into one portable, content-addressed Evidence Pack that any agent can
attach to a handoff or CI run.

### Command contract implemented

```bash
# Explicit execution only; `--` separates the trace options from the command.
aet trace --output .aet/evidence/trace.json -- <command> [args...]

# Compile independently generated audit, review, and trace artifacts.
aet evidence pack \
  --audit .aet/evidence/audit.json \
  --review .aet/evidence/review.json \
  --trace .aet/evidence/trace.json \
  --output .aet/evidence/evidence-pack.json
```

### Design decisions implemented

1. `trace` is opt-in and executes only the explicit argv after `--`; neither
   audit nor review may start executing commands implicitly.
2. Store argv, exit code, start/finish timestamps, working directory, Git HEAD
   and diff digest, plus SHA-256 digests of captured stdout/stderr artifacts.
   Do not write raw output to the Evidence Pack by default.
3. Redact configured secret patterns from command metadata and persisted log
   excerpts. If redaction confidence is insufficient, mark the field
   `UNKNOWN` rather than retaining the value.
4. `evidence pack` validates the input report schemas, records each input's
   SHA-256, preserves `PASS`/`FAIL`/`UNKNOWN` without collapsing them to a
   score, and writes atomically.
5. Inputs may be absent, but the pack must record the missing component as
   `UNKNOWN` and never imply that a test or review happened.
6. Keep the format host-neutral JSON. It must be consumable by any agent that
   can read files; no MCP, model API, or vendor trace API is permitted.

### Acceptance checks completed

- Unit tests cover a successful command, a non-zero command, secret redaction,
  stable hashing, invalid input schema, missing optional inputs, and atomic
  output replacement.
- A clean temporary Git fixture produces audit → review → trace → pack with
  source hashes and no fabricated status.
- A failing command has a recorded non-zero status and a valid Trace artifact;
  it does not become a successful proof.
- Build and install the 0.3.0 wheel in a fresh virtual environment.
- Upgrade the canonical and local cross-agent Skill to 0.3.0, update this
  memory with actual results, commit, and tag `v0.3.0`.

## After v0.3

The static core will be complete. Repo Archaeologist remains `aet evolve` and
must not become a dependency of audit, review, trace, or Evidence Pack. No
model-generated judgement should be the sole release gate.

## Productization design — 2026-07-11

The complete post-v0.3 product plan is recorded in
`docs/productization-plan.md`. It was produced from the original “设计 Agent
工具包方案” conversation, the active repository at `v0.3.0`, and a source
review of `yaojingang/yao-meta-skill` at commit
`4eb11f923dc71173736ebf541a7eebfff942d10e`.

### Decision

`aet` is an Evidence Plane, not a general-purpose Skill OS. Its stable product
surfaces are Context/Skill Hygiene (`audit`), Intent Change Control (`review`),
Execution Evidence (`trace`/`evidence pack`), and Repository Evolution
(`aet evolve`). Repo Archaeologist is therefore a first-class usage scenario
of the canonical cross-agent Skill, but remains independent of the offline
deterministic core.

### Product rules added

1. Reuse an Evidence IR with source hashes and verification levels; preserve
   `PASS`/`FAIL`/`UNKNOWN` rather than creating a health score.
2. Scores may only prioritize reviewer work; they cannot release a change or
   convert an unknown into a pass.
3. `evolve` must distinguish direct, corroborated, candidate, and unknown
   links across Git, docs, releases, PRs, and Issues. Model narration is an
   optional, provenance-bound inference and cannot become source evidence.
4. Implement `v0.3.1` first: fix the stale README v0.3 claim, add auditable
   discovery excludes/config, and make self-audit usable despite intentional
   failing fixtures. Then execute v0.4 Evidence IR/proof binding, v0.5 Skill
   UX/governance, v0.6 offline evolve, and v0.7 GitHub evolve.

### Current planning findings (not yet fixed)

- `aet audit . --strict` produces expected FAIL/UNKNOWN results from
  `tests/fixtures/broken_project`, proving the current discovery layer lacks
  a configurable test-fixture boundary.
- `README.md` still contains an obsolete statement that v0.3 Trace and
  Evidence Pack are planned/not implemented, although `v0.3.0` implements
  them. This is a documentation defect.
- This entry is a design/memory update only; no v0.3 behavior was changed and
  no new release tag has been created. Resume implementation from the v0.3.1
  acceptance criteria in the productization plan.

## Known limits

- v0.1 parses local Markdown and paths; it cannot prove that a remote MCP
  server is reachable or that a command semantically succeeds.
- Detection is intentionally conservative. A missing local target is a FAIL;
  a remote, dynamic, or bare filename is left unverified rather than guessed.
- Repo Archaeologist needs GitHub history, Issues, PRs, and releases, so it is
  deferred behind the stable evidence schema.

## v1.0.0 implementation and release candidate — 2026-07-11

- Implemented the Evidence Plane: configurable `audit`, intent `review`, proof-bound `trace` / Evidence Pack / static viewer, transparent non-gating `triage`, and `aet evolve` as the Repo Archaeologist surface (plan, local Git/docs, export or explicit GitHub API, graph, report, query).
- Added Evidence IR metadata and L0–L5 boundaries while preserving `PASS`/`FAIL`/`UNKNOWN` as authoritative. Weighted triage factors are visible and cannot alter a gate.
- Fixed self-audit with reasoned `aet.toml` exclusion for intentionally broken fixtures. Added stale absolute-path detection after auditing Codex global `AGENTS.md`, whose Skill index can drift from installed paths.
- Scoped Codex `AGENTS.md` dogfood found 52 stale absolute Skill paths and one root-context-bloat warning; the audit did not mutate global instructions.
- Added v1 README, contracts, schema, canonical Skill flow, changelog, CI and tag-driven GitHub release workflow.
- Before tagging, require strict self-audit, full unit suite, wheel plus isolated CLI smoke, a proof-bound Evidence Pack, GitHub audit/evolution evidence, and a clean intentional commit.

## Documentation and community entrypoint — 2026-07-11

- Reworked the English README from a command-first reference into a product
  entrypoint: user problem, four capability surfaces, evidence architecture,
  verified quality boundary, install paths, workflow guides, Repo
  Archaeologist, audience fit, and repository map.
- Added `docs/README.zh-CN.md` as the complete Simplified Chinese companion,
  with an explicit language switch at the top of both README files.
- Added `CONTRIBUTING.md`, a copyable generic intent example, and GitHub Issue
  forms so external users can report sanitized evidence-boundary defects or
  propose concrete workflows without exposing private repository content.
- GitHub discovery metadata should describe AET as evidence-first engineering
  guardrails for coding agents and use focused topics rather than broad AI
  hype. Keep public claims tied to reproducible release checks; do not claim
  PyPI publication unless it actually occurs.

## v1.3.0 implementation and release candidate — 2026-07-12

- Added `aet context discover`, `record`, and `verify`. The Context Manifest
  records local instruction/Skill discovery and hashes; a declared read is
  explicitly an `agent_attestation`, never evidence that a model understood or
  used the file.
- Added the local JSON Decision Ledger with `init`, `add`, `list`, `verify`,
  and `supersede`. It stores source hashes, evidence state, lifecycle state,
  and replacement history; it is project decision provenance, not generic
  Agent memory or RAG.
- Regression coverage now includes both a clean and a changed-source/context
  path, as well as direct supersession. The v1.3 release gate requires 27 unit
  tests, strict self-audit, reviewed intent, a proof-bound Trace/Evidence Pack,
  and an isolated wheel smoke test.
