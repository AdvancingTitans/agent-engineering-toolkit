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

`aet` is an Evidence First toolkit for lightweight investigation of AI coding
scope, real command execution, and proof freshness. Quick is read-only by
default; only an explicit `/aet-proof` argv executes project code and writes
the requested compact Receipt. AET reports unknowns and never invents a
holistic trust score.

Primary users are individual developers and small teams using Codex, Claude
Code, Cursor, Copilot, or compatible agent Skills across multiple repositories.

The default product surface is four dedicated cross-agent Skills:
`aet-check`, `aet-scope`, `aet-proof`, and `aet-fresh`; the `aet` CLI is their
deterministic local runtime. The canonical `agent-engineering-toolkit` Skill is
the compatibility and explicit AET Lab route. Every shipped capability retains
machine-readable evidence contracts so any Agent Host can invoke it.

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

## v1.4.0 implementation and release candidate — 2026-07-12

- Invest-Vault dogfood confirmed that v1.3 Trace successfully ran its complete
  pytest process; the gap was report portability, not subprocess execution.
  Trace held stdout/stderr but not a test framework's generated report.
- Added explicit `trace --artifact <relative-path>` capture. It is not a
  report-file guesser: only a declared regular UTF-8 file under the workspace
  is captured, redacted, hashed, and embedded into Trace plus Evidence Pack.
- A missing, outside-root, non-regular, undecodable, or unredactable declared
  artifact is `UNKNOWN`. AET returns non-zero after an otherwise successful
  child command, while preserving the child's `execution: PASS` fact.
- A real pytest dogfood trace initially exposed unrelated collection of nested
  `work/dogfood` repositories. `pyproject.toml` now limits optional pytest
  discovery to AET's own `tests/` directory.
- This adopts the useful Harness Engineering idea of durable, inspectable
  filesystem artifacts and failure traces. It explicitly rejects the article's
  broader runtime, autonomous optimization, and generic-memory directions.
- The v1.4 release gate requires 30 unit tests, a real pytest JUnit artifact
  dogfood trace/pack, strict self-audit, reviewed intent, a proof-bound release
  Evidence Pack, and an isolated wheel smoke test.

## v1.12.0 Repository Audit Showcase release candidate — 2026-07-23

- Added three commit-locked, static-only cases: SWE-agent
  `3ea751c087f32b16e039a2233dd6eefecef325d5`, Google ADK
  `67ab27f2547db48f7248b1689aab4c18502aee17`, and OpenHands
  `96f902a9ac14bf5edfb2e47d759d75c91e4faf28`.
- Added the independent `repository-audit-profile/v1` contract and
  `aet audit swe-agent|google-adk|openhands --repo <checkout>`. Existing
  `aet audit <path>` behavior and `audit-profile/v1` remain unchanged.
- Each case writes two shared machine artifacts and five human-readable
  artifacts under both `en/` and `zh-CN/`. Findings are deterministic,
  evidence-located engineering observations; no holistic score, upstream code
  execution, upstream test execution, source redistribution, or LLM-authored
  Finding is permitted.
- The measured runtime includes evidence collection, rule analysis, complete
  report rendering, and staged artifact writes. Clone, dependency installation,
  LLM network time, and manual review remain outside the 900-second contract.
- OpenHands `enterprise/**` and `tests/**/enterprise/**` are prohibited. The
  latest upstream has moved its Agent core into separately versioned
  dependencies, so the local Agent-core claim remains `UNKNOWN`.
- The maintainer approved all three bilingual report snapshots after
  English/Chinese parity review and desktop/mobile visual inspection; their
  tracked `review.status` is `APPROVED`. New runs still default to `PENDING`.
- Acceptance evidence: 12 focused repository-audit tests passed; the full
  regression gate passed 216 tests; the complete business-quality gate passed
  75 tests and 237 subtests; the wheel built and returned version `1.12.0` in an
  isolated environment. All three Chinese HTML reports passed a 390 × 844
  viewport check with no overflow or broken images.
- Remaining release work is operational: bind the final Diff in
  `release-classification.json`, commit, tag, push, wait for exact-commit CI,
  and publish GitHub Release `v1.12.0`. Do not publish to PyPI.

## Unreleased AET Quick implementation — 2026-07-24

- Reframed the default product surface around four independent, bounded Skills:
  `/aet-check`, `/aet-scope`, `/aet-proof`, and `/aet-fresh`. Each emits one
  result and stops. Existing 1.x CLI and AET Lab surfaces remain compatible and
  require explicit opt-in.
- Added `aet quick check|scope|proof|fresh`. The new layer reuses the existing
  deterministic audit, Git, Trace, snapshot, redaction, and receipt core rather
  than changing legacy command semantics.
- Added host-neutral investigation contracts and standard-library validation
  for Intent provenance, competing hypotheses, immutable result references,
  counter-explanation requirements, Finding strength, tool authority, write and
  execution permission, command budgets, and stop conditions.
- Preserved `PASS`/`FAIL`/`UNKNOWN`/`NOT_APPLICABLE` as authoritative evidence
  status. Finding origin and semantic support remain in the Investigated
  Finding contract; Scope disposition and Freshness state remain command-level
  fields and cannot overwrite source evidence.
- Quick Proof writes one compact JSON receipt after an explicit request and
  records argv, exit status, workspace snapshot, relevant paths, artifacts,
  the selected executable identity, explicitly named environment-input hashes,
  Python/platform identity, and dependency lockfile hashes. Quick Fresh
  distinguishes exact, unrelated-workspace, HEAD-only, relevant-file, artifact,
  environment, and unknown drift while retaining legacy evidence fallback.
- Added deterministic narrative routing: only a Chinese slash-command request
  defaults to Simplified Chinese; all other requests use English. Rendering
  changes no machine state or evidence reference.
- Rebuilt the English and Simplified Chinese README around Quick, added four
  dedicated portable Skills, six JSON Schemas, synchronized static and
  animated SVG architecture sources, 1600 × 900 PNG renders, and English and
  Chinese WebM introductions. The three commit-locked Repository Audit Showcase
  cases remain unchanged and are documented as AET Lab.
- Completed the full Investigation Contract runtime: contract shape,
  `finding_type`, explicit-user source references, negative-search coverage,
  material recorded conflicts, semantic disclosure, and allowed stop reasons
  are now checked by the standard-library Grounding Validator. The Validator
  always validates the supplied Ledger before trusting its references.
- Added the opt-in `eval/quick-investigation/` AET Lab harness with the four
  frozen comparison groups and eight Scope scenarios. A real `gpt-5.6-sol`
  / medium, two-repetition run produced 64 observations. Effective recall /
  false discovery proportions were 60% / 50% for pure rules, 80% / 38.5% for
  one-shot LLM, and 90% / 25% for both investigated groups. The Grounded
  group used the shipped Validator and rejected zero claims in this sample.
  The tracked result records time, tools, and Tokens; unmeasured manual-review
  time and user understanding remain `UNKNOWN`.
- Acceptance evidence in the working tree: 260 unit tests passed; strict
  self-audit returned zero findings; an isolated wheel contained the Quick,
  investigation, narrative, built-in RulePack, and new Schema assets, exposed
  all four Quick subcommands, reported version `1.13.0`, and passed a legacy
  Audit smoke test. The runnable stale-proof demo produced `EXACT_MATCH` and
  then `RELEVANT_FILES_CHANGED`.
  The tracked 30-sample performance report measured Check P95 0.622 s, Scope
  P95 0.059 s, and Fresh P95 0.037 s on the recorded local environment. These
  are local bounded checks, not cross-repository or model-service P95 claims.
- Released `v1.13.0` from commit
  `2683479cc742775674be75483fdb1606b62b3e60` on 2026-07-25. Exact-commit CI
  Run `30113760362` and GitHub Release Run `30113835956` passed; the Release
  publishes the Wheel, sdist, CI manifest, Diff-bound classification, verified
  classification, and release-evidence record at
  `https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/tag/v1.13.0`.
  Real Host Gate is `NOT_APPLICABLE` because this deterministic release adopts
  no governance asset and makes no release-authorizing Agent behavior claim.

## README media refresh — 2026-07-25

- Replaced the README architecture media with bilingual, motion-validated AET
  Quick workflow GIFs and bilingual static project panoramas. The panorama
  distinguishes the Quick request path, shared protocol support, human
  authority, and the explicit AET Lab entrance; every arrow terminates at a
  named component or authority boundary.
- Replaced the former WebM introductions with exact 30-second English and
  Simplified Chinese H.264/AAC MP4 videos. The tracked media manifest binds all
  published GIF, SVG, PNG, and MP4 assets by SHA-256.
- Reworked both READMEs around daily Agent coding problems, bounded product
  promises, measurable evaluation trade-offs, the distinct roles of
  grounding-aware investigation and the in-project Grounding Validator, and
  Chinese explanations for internal evidence terminology. Chinese documentation
  and generated media consistently use “契约”.

## v1.14.0 Portable Evidence Bundle release candidate — 2026-07-26

- Added Codex and Claude Code Run Normalizers, stable source identity,
  incremental ingestion, tool-call/result linking, generation boundaries, and
  fail-visible diagnostics. Run Records establish only what the normalized run
  contains.
- Added strict Observation, Evidence Candidate, Verified Evidence, and Portable
  Claim boundaries. Every exported Observation declares what it proves and
  does not prove; model reasoning and recorded tool output cannot become
  reproduced evidence without deterministic verification.
- Added deterministic Candidate verification for explicitly authorized AET
  Proof receipts. Command, workspace, budget, path, receipt integrity, and
  Freshness bindings are enforced; stale results remain historical and cannot
  become current proof. Added the bounded OptimizationCandidate entry contract
  with independent-task/high-severity evidence prerequisites and mandatory
  isolated evaluation.
- Added the read-only Portable Investigator, immutable investigation ledger,
  JSON Schemas, Bundle Compiler, strict loader/validator, canonical hashing,
  redaction, Index/Core/Archive layout, content-addressed Blobs, deterministic
  Markdown, Review Result validation, bounded MCP server, and optional Python
  and TypeScript SDKs. A reviewer can consume the Bundle without installing
  AET or either SDK.
- Real prompt-only consumption checks used ten deterministic synthetic Bundles.
  Codex CLI 0.144.1 / `gpt-5.6-sol`, Hermes Agent 0.17.0 / `kimi-k2.6`, and
  Ollama 0.32.3 / `qwen3:8b` each produced strict, independently rescorable JSON
  for all ten scenarios: 62 `PASS`, 38 `NOT_APPLICABLE`, zero `FAIL`, and zero
  `UNKNOWN`. Runtime, model, elapsed time, command-argv digest, response,
  report, and publication integrity are tracked. These results are a bounded
  interoperability check, not a general accuracy claim or trust score.
- The English and Simplified Chinese READMEs now describe the complete Quick
  and portable handoff surfaces. Their static SVG/PNG panoramas, 115-frame
  motion-validated GIFs, exact 30-second H.264/AAC videos, and media Manifest
  reflect v1.14.0.
- Acceptance evidence: 418 Python unit tests passed after a non-editable
  reinstall; the TypeScript Bundle SDK passed 11 adversarial tests, Node 20
  build/compatibility checks, and package dry-runs; the Python wheel and sdist
  built successfully and the isolated wheel validated a Bundle plus the
  packaged Optimization Schema; all Bundle result and media hashes were
  independently recomputed; strict Hermes/Ollama responses were independently
  reparsed and rescored; README links, forbidden-name scan, and
  `git diff --check` passed.
- Released `v1.14.0` from commit
  `fee324fe1ee5681035e15b146d3fab8ccaee7f12`. Exact-tag CI Run
  `30171294767` passed, the Diff-bound classification verified all 58
  behavior-sensitive paths, and the public GitHub Release is available at
  `https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/tag/v1.14.0`.
  Its five assets include the exact CI wheel and sdist, CI Manifest, release
  classification, and classification verification report. No governance asset
  was adopted and the Real Host Gate is `NOT_APPLICABLE`.
- Resume point: begin the next change from `v1.14.0`; preserve the Portable
  Evidence Bundle v1 compatibility and do not reinterpret the bounded
  Hermes/Ollama/Codex fixture results as a general accuracy claim.

## v1.15.0 Evidence Atlas release — 2026-07-26

- Added Evidence Atlas as a deterministic derived layer over Portable Evidence
  Bundle v1: a canonical source-backed Graph, eight fixed Perspectives,
  bounded typed recursive decomposition, Mermaid/Markdown/JSON projections,
  strict provenance and Schema validation, incremental rebuilds, Atlas Diff,
  and an offline recursive Viewer. Graph records remain authoritative;
  Mermaid, documents, and Viewer state create no evidence or authority.
- Added `aet atlas build|validate|view|export|query|explain|diff`, including
  comma-separated `--perspectives` selection and no-LLM operation. The Python
  and TypeScript SDKs expose graph build/load/query/trace/validate/render
  surfaces, and MCP exposes eight bounded read-only `aet_graph_*` tools.
- Freshness timelines use the recorded `checked_at` value, normalized only to
  Mermaid-safe punctuation, and show `UNKNOWN` when no timestamp is recorded.
  Current, stale, conflict, counter-evidence, limitation, `does_not_prove`,
  missing Change Group, cycle, deduplication, and maximum-depth semantics have
  direct regression coverage. Malformed Mermaid declarations fail closed.
- The English and Simplified Chinese READMEs now position Evidence Atlas,
  present bilingual static architecture, a real six-state recursive Viewer
  GIF, exact 30-second H.264 walkthroughs, the end-to-end flow, and an exact
  tracked Mermaid Claim Chain generated from AET's source-bound self-review.
  The example narrowly states what the Portable Evidence v1 Evidence record
  Schema establishes and retains its unresolved Change Group boundary.
- Acceptance evidence in the release-candidate working tree: 444 Python unit
  tests passed after a non-editable reinstall; the TypeScript SDK passed 16
  tests plus its built-distribution smoke test; the Viewer runtime check
  passed; Mermaid 11.16.0 parsed all 93 recursive diagrams from both the source
  and isolated-wheel Atlas; seven media files matched their recorded byte
  lengths and SHA-256 values; `git diff --check` passed. Fresh Wheel and sdist
  were rebuilt, and the isolated Wheel reported `1.15.0`, contained the
  vendored Mermaid runtime and all ten Atlas Schemas, rejected
  `flowchart BOGUS`, built and validated the real self-review Atlas, and kept
  explicit `does_not_prove` documentation.
- The first exact-tag CI attempt, Run `30202354466`, passed the full Python,
  stale-proof, and real-agent gates, then failed before parsing because
  `npm --prefix` resolved the relative Atlas argument from the package
  directory. No Release was created. CI now passes the explicit
  `$GITHUB_WORKSPACE/.aet/evidence/atlas-self-review.atlas` path, and the
  delivery-gate test freezes that binding.
- The final independent compliance audit approved publication with no remaining
  P0/P1 or acceptance gap. Released `v1.15.0` from commit
  `039cc5a10f4ee2a9c9056060f48af671e060f5c9`; exact-tag CI Run
  `30202586689` and GitHub Release Run `30202642550` passed. The public
  Release publishes the exact CI Wheel, sdist, CI Manifest, Diff-bound
  classification, classification verification, and release-evidence record at
  `https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/tag/v1.15.0`.
  Real Host Gate is `NOT_APPLICABLE`, and no PyPI publication was performed.
- Resume point: begin the next change from `v1.15.0`; preserve Portable
  Evidence Bundle v1 compatibility, the deterministic Graph authority
  boundary, explicit counter-evidence/`UNKNOWN`/Freshness semantics, and the
  seven pre-existing untracked files outside version control.

## v1.16.0 Evidence-Grounded Improvement release — 2026-07-29

- Added the planned deterministic `src/aet/improvement/` subsystem with
  Issue, Constraint, Candidate, Verification Contract, and Outcome models;
  Finding normalization/aggregation; bounded rules; human/Agent/PR renderers;
  Candidate grounding, Scope, reference, strength, and anti-gaming validators;
  and the Proof-bound verification lifecycle.
- Added `aet improvement doctor`, `aet improve <bundle>`, and the
  `prompt`, `validate`, `verify`, and `compare` Improvement actions. Candidate
  state remains `PROPOSED`; `verified_improvement` requires a recorded code
  change, current contract-bound passing Proof, and no comparison regression.
- Portable Evidence Bundle v1 has no independent Finding or Improvement
  collection. The deterministic adapter consumes validated portable Claims as
  Finding-compatible inputs without changing Bundle, Evidence, or Finding
  schemas. Missing independent Improvement records remain explicit `UNKNOWN`.
- Added the non-blocking, no-LLM PR Improvement Summary workflow and the
  `improvement-chain` / `regression-lineage` Atlas Perspectives. Python Atlas
  schemas, MCP description, and the TypeScript SDK now agree on ten fixed
  Perspectives.
- Added a reproducible empty-tool-result review case. Its failing regression
  evidence grounds `IMP-001`, a human report, and a bounded `PROPOSED` Agent
  task. The same Bundle independently drives Claim Chain and Improvement Chain
  Atlas views; the latter remains `UNKNOWN` because Bundle v1 has no
  independent Improvement records.
- Updated the English and Simplified Chinese READMEs, static architecture,
  animated workflow, project panorama, Atlas architecture, and silent 30-second
  H.264 product/Atlas videos. Added bilingual case SVG/PNG/GIF media and
  SHA-256 manifests. Geometry, composition, semantic motion, frame, hash, and
  manual visual checks passed.
- Added six planned Golden Fixture families and `docs/improvement.md`. Final
  acceptance: unittest discovered 478 passing tests; the release-gate pytest
  run passed 488 tests and 636 subtests; TypeScript SDK 16/16, distribution
  smoke 1/1, compatibility guard, Viewer/Mermaid, stale-proof, four suites,
  strict audit, build, isolated Wheel smoke, and `git diff --check` passed.
- Remaining unmeasured product targets are the SC-001 human comprehension
  percentage and real Codex/Claude `pass@1` / `pass^3` execution metrics.
  CI publication behavior has local contract coverage but has not been
  observed on a live pull request.
- Released `v1.16.0` from commit
  `bfe062a9f68b805a5b629f32828510a411c9a1f9`. Exact-tag CI Run
  `30420607956` and GitHub Release Run `30420768704` passed. Release ID
  `361498297` publishes the exact CI Wheel, sdist, manifest, Diff-bound
  classification, classification verification, and release-evidence record at
  `https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/tag/v1.16.0`.
  Real Host Gate is `NOT_APPLICABLE`; no PyPI publication was performed.
- Resume point: begin the next change from `v1.16.0`; preserve Bundle v1
  compatibility, Graph authority, prompt/Atlas sibling projection, explicit
  counter-evidence/`UNKNOWN` semantics, and the seven pre-existing untracked
  files outside version control. Real Agent and user-comprehension metrics
  remain unmeasured.
