# Changelog

## 1.18.0 — 2026-07-29

- Added an installed-wheel `aet demo stale-proof` path that runs a real
  standard-library test, records Proof with the existing Quick API, verifies
  `EXACT_MATCH`, mutates a declared source, and verifies
  `RELEVANT_FILES_CHANGED`.
- Reframed the first-run experience around proof-carrying workflows for coding
  agents, with focused English and Simplified Chinese documentation, a static
  no-tracking site, community guidance, and reproducible visual assets.
- Added strict Skills catalog validation, a read-only GitHub Action template,
  launch-readiness checks, and privacy-preserving growth snapshots. All
  external publication, repository settings, and outreach remain manual.
- This activation and distribution release does not change core Evidence
  authority semantics: tests and Proof remain source-bound, missing facts
  remain explicit, and human adoption and release authority are unchanged.

## 1.17.0 — 2026-07-29

- Added Evidence-Guided Planner as a read-only Host boundary:
  deterministic Planning Request and Context construction from validated
  Bundle, optional matching Atlas, current hash-bound Source, existing scope,
  and explicit budgets; Host reasoning returns strict Candidate JSON, and AET
  alone validates the portable `PROPOSED` Plan.
- Added six strict Planning v1 Schemas, fail-closed identity/reference/path and
  protected-scope validation, explicit `READY_FOR_HUMAN_REVIEW`,
  `NEEDS_EVIDENCE`, `PARTIAL`, `BLOCKED`, and `SUPERSEDED` status, four Edit
  dispositions, counter-evidence/conflict/UNKNOWN preservation, and guarded
  `BOUNDED_COMPLETE` coverage.
- Added `aet plan context|validate-candidate|validate|show|explain|trace|gaps|
  export-skill|verification-handoff`, deterministic Markdown and portable
  Plan packages, single-Plan Host Skill export, and external-diff handoff that
  leaves Proof `UNKNOWN` and `PENDING` instead of executing it.
- Added the thin `/aet-plan` Host Skill, eight bounded Planning MCP tools,
  Python SDK helpers, and `loadPlan`, `queryPlanEdits`, and
  `validatePlanReferences` in the existing TypeScript Bundle SDK. No model
  client, Agent loop, source editor, or Executor was added.
- Added three reproducible end-to-end examples and a separately frozen,
  20-case, three-group localization benchmark. Release language is deliberately
  “bounded localization”; it does not claim to find every modification point.
- Added English and Simplified Chinese product navigation, complete Planner,
  Helper, Schema, architecture, security, SDK, MCP, example, and verification
  handoff documentation.
- Added a reproducible real Codex `gpt-5.6-sol` AET self-review with separate
  source-only, v1.16 evidence-only, and v1.17 validated-Plan observations. The
  checked-in Gold, raw structured outputs, deterministic scorer, and result
  report eight independent scope-localization metrics without a holistic
  score. In this one-run-per-group case, v1.17 raised production-path decision
  precision from 44.44% to 100%, linkage coverage from 33.33% to 100%, and
  `UNKNOWN` preservation from 0% to 100%; path/test recall was already 100% in
  source-only and did not improve.
- Rebuilt the bilingual README Planner story, dynamic/static architecture,
  real-case screenshots, project panoramas, and exact 30-second silent H.264
  introductions. SHA-256 manifests bind the generated workflow, review contact
  sheets, screenshots, panoramas, and videos.

## 1.16.0 — 2026-07-29

- Added the deterministic Evidence-Grounded Improvement Layer: validated
  Portable Evidence Bundle records become bounded Improvement Issues,
  Constraints, human reports, `PROPOSED` Agent tasks, Verification Contracts,
  and outcomes without editing code or granting recommendations evidence
  authority.
- Added `aet improvement doctor` and `aet improve
  <bundle>|prompt|validate|verify|compare`, strict grounding/scope/strength and
  anti-gaming checks, protected-path enforcement, Proof/Freshness binding, and
  before/after comparison that retains `PASS`, `FAIL`, `UNKNOWN`, and
  `NOT_APPLICABLE`.
- Extended Evidence Atlas from eight to ten fixed Perspectives with
  Improvement Chain and Regression Lineage. Bundle v1 has no independent
  Improvement records, so these views remain explicitly `UNKNOWN` until
  source-bound records exist; prompts never write back as Evidence.
- Added a reproducible project-review case in which an empty tool result is
  incorrectly emitted as “no issues.” A real failing regression becomes
  counter-evidence for `IMP-001`, grounding the human report, one-file Agent
  scope, verification command, and Claim/Improvement Chain diagrams.
- Fixed Mermaid rendering so unsupported Claims use a distinct red dashed
  class instead of the supported-Claim style.
- Rebuilt the English and Simplified Chinese README product narrative,
  commands, architecture and process diagrams, real-case GIF/PNG/SVG assets,
  Evidence Atlas visuals, and silent 30-second H.264 introduction videos with
  refreshed SHA-256 manifests.

## 1.15.0 — 2026-07-26

- Added Evidence Atlas, a deterministic canonical Evidence Graph derived from
  Portable Evidence Bundle v1 records. Authoritative nodes and edges retain
  field-level source references; stale Proofs cannot validate current Claims,
  counter-evidence remains visible, and missing facts remain `UNKNOWN`.
- Added eight fixed Perspectives for Claim Chain, Investigation Flow, Change
  Scope, Verification Coverage, Evidence Data Flow, Integrations, Conflicts,
  and Freshness. Every node receives deterministic complexity evaluation;
  typed recursive decomposition, canonical-node deduplication, cycle stops, and
  hard depth/node/child/diagram budgets keep diagrams bounded.
- Added safe Diagram IR and Mermaid projection, structured Markdown and JSON,
  strict validation, and a completely offline three-column Viewer with local
  Mermaid, search, filters, supporting/counter/stale path highlighting,
  evidence details, and recursive parent/child navigation.
- Added `aet atlas build|validate|view|export|query|explain|diff`, optional
  Python and TypeScript graph APIs, and eight bounded read-only MCP graph tools.
  Incremental rebuilds reuse validated unchanged Perspectives and unaffected
  recursive subgraphs; Atlas
  comparison reports Claim, Freshness, conflict, and unknown changes without a
  holistic trust score.
- Added JSON Schemas, security and failure fixtures, protocol tests, and a
  reproducible AET self-review Bundle whose real Claim Chain and offline Viewer
  drive the README example.
- Updated the English and Simplified Chinese product showcase with synchronized
  static Evidence Atlas architecture, a six-state real Viewer GIF, 30-second
  bilingual H.264 walkthroughs, a SHA-256 media manifest, and a GitHub-rendered
  Mermaid self-review example.

## 1.14.0 — 2026-07-26

- Added host-neutral Codex and Claude Code Run Normalizers with stable record
  identity, content hashes, tool-call/result linking, incremental ingestion,
  generation boundaries, and explicit diagnostics.
- Added the strict Observation → Evidence Candidate → Verified Evidence
  boundary. Agent statements, reasoning, and recorded tool output cannot become
  reproduced proof without deterministic workspace-bound verification.
- Added the read-only Portable Investigator with primary and competing
  hypotheses, disconfirming search, privacy policy, budgets, stop conditions,
  immutable ledger output, and fail-closed `UNKNOWN` handling. Explicitly
  authorized AET Proof receipts can now verify matching command Candidates
  against the declared read-only workspace; Freshness drift preserves the
  historical result while preventing promotion to current proof.
- Added Portable Evidence Bundle v1: self-describing Index/Core/Archive JSON
  and JSONL, deterministic Markdown, content-addressed Blobs, Freshness,
  counter-evidence, conflicts, diagnostics, canonical hashing, strict schema
  validation, and optional structured Review Result validation. Reviewers do
  not need AET or an SDK installed.
- Added bounded CLI and MCP operations plus optional Python and TypeScript
  Bundle SDKs. The TypeScript package ships a Node 20-compatible JavaScript
  distribution, deep-frozen trusted handles, strict duplicate-key parsing, and
  adversarial tests for forged claims, evidence, enums, links, and Blobs.
- Added ten deterministic consumption scenarios and independently rescorable
  prompt-only measurements for Codex CLI 0.144.1 / `gpt-5.6-sol`, Hermes Agent
  0.17.0 / `kimi-k2.6`, and Ollama 0.32.3 / `qwen3:8b`. Every consumer produced
  strict JSON covering all ten scenarios with 62 `PASS`, 38
  `NOT_APPLICABLE`, zero `FAIL`, and zero `UNKNOWN`; these are bounded
  synthetic-fixture interoperability results, not general accuracy or trust
  scores.
- Rebuilt the English and Simplified Chinese README showcase around the current
  portable evidence architecture, including synchronized static SVG/PNG
  panoramas, validated 5.75-second bilingual GIF workflows, exact 30-second
  bilingual H.264/AAC product videos, and a SHA-256 media manifest.
- Added the bounded `OptimizationCandidate` entry contract. It requires
  multiple independent tasks or an explicit current high-severity
  deterministic failure, always requires isolated evaluation, and cannot
  modify a Skill, adopt a candidate, or publish a release.

## 1.13.0 — 2026-07-25
- Added the four bounded AET Quick surfaces: Check, Scope, Proof, and Fresh,
  while preserving the legacy 1.x `audit`, `review`, `trace`, receipt, and Lab
  commands.
- Added host-neutral Intent, Investigation Ledger, Investigation Contract,
  Investigated Finding, and Command Budget contracts plus deterministic
  grounding, permission, source, search-scope, recorded-conflict, contract-shape,
  and stop-policy validation.
- Added relevant-file, artifact, runtime, and lockfile binding to minimal Quick
  proof receipts, with seven explicit freshness states.
- Added dedicated portable Skills and deterministic language routing: a Chinese
  slash-command request receives natural Simplified Chinese narrative; every
  other request defaults to English. Machine statuses and evidence references
  remain language-neutral.
- Rebuilt the English and Simplified Chinese product entrypoints around AET
  Quick, with synchronized static/animated architecture, bilingual introduction
  videos, and the existing commit-locked Repository Audit Showcase retained as
  an explicit AET Lab case library.
- Added an opt-in AET Lab comparison across pure rules, one-shot LLM,
  investigated AET, and a distinct Grounding-aware Agent configuration plus the
  shipped Grounding Validator. The eight-case, two-repetition result publishes
  64 privacy-reviewed normalized Runs for independent rescoring and records
  recall, false discovery proportion, ungrounded conclusions, tool calls, wall
  time, and Tokens while leaving unmeasured human-review and understanding
  metrics `UNKNOWN`.
- Added a tracked 30-sample local performance report with raw Check, Scope, and
  Fresh timings, nearest-rank P95, environment, repository size, and explicit
  limits.

## 1.12.0 — 2026-07-23

- Added the Repository Audit Showcase for commit-locked SWE-agent, Google ADK,
  and OpenHands checkouts, with independent
  `repository-audit-profile/v1` profiles and the
  `aet audit <case> --repo <checkout>` CLI.
- Added deterministic, static-only evidence collection and findings. Upstream
  code and tests are never executed; LLM narration is off and cannot change a
  Finding; `PASS`/`FAIL`/`UNKNOWN`/`NOT_APPLICABLE` remain authoritative.
- Added profile, result, and evidence-manifest JSON Schemas, shared machine
  artifacts, and complete English/Simplified Chinese summaries, Markdown,
  HTML, Agent-flow SVGs, and evidence-chain SVGs.
- Locked each upstream commit and License boundary. OpenHands
  `enterprise/**` content is prohibited, and its externally versioned Agent
  core remains an explicit `UNKNOWN` rather than a guessed local capability.
- Added bounded-path, symbolic-link, stale-output, Schema, false-positive,
  runtime-budget, CLI-compatibility, and no-source-redistribution regression
  coverage.

## 1.11.1 — 2026-07-14

- Reworked the bilingual entrypoint around one concrete failure: a passing test
  log becomes stale when the workspace changes. Added a runnable stale-proof
  demo and case study that preserve historical execution success while failing
  current freshness.
- Published the AET 1.x stability contract and moved three focused contribution
  paths near the top of both READMEs.
- Added a focused PyPI project page, complete package metadata and an OIDC
  Trusted Publishing workflow that promotes only the exact wheel already built
  and hash-verified by CI.

## 1.11.0 — 2026-07-14

- Replaced the universal six-pair Real Host release constant with a
  pre-registered `gate-plan/v2`. Plans bind Claim, risk, Candidate, Runner,
  configuration, Scorer, Task and Fixture bytes; R3/R4 plans include an exact
  directional power analysis and risk-declared effect assumptions.
- Split observed Suite semantics: Core is a zero-hard-regression,
  all-candidate-tasks-pass retention contract; Validation and Held-out use
  explicit one-sided exact paired objectives plus MCID. Legacy commands retain
  their historical two-sided McNemar behavior.
- Added dependency-free Bonferroni group-sequential alpha spending, efficacy,
  hard-regression, infrastructure, mathematically safe futility and maximum-N
  stopping reasons. Ordinary fixed-sample p-values cannot be repeatedly peeked.
- Added full observed-task preflight before the first Host call, append-safe
  replay checkpoints, explicit exact `--resume`, and same-run replay reuse for
  Tournament. Sleep no longer performs a duplicate Replay before Gate, and
  Held-out is not opened after a preceding objective fails.
- Added strict `gate-history-registry/v1` and planning-only history assessment.
  Entries require verified PASS provenance, exact identity, count consistency
  and deduplication. Drift, discount caps and leave-one-release-out sensitivity
  are reported; historical observations never enter PASS and never lower the
  fresh-pair planned maximum.
- Reduced the portable root Skill from 262 lines / 14,401 bytes to 99 lines /
  5,926 bytes by routing to on-demand delivery, provenance, quality, evolution
  and security references while preserving default-off activation and immutable
  authority boundaries.
- Removed repeated CI test subsets, added concurrency cancellation, and changed
  Release to verify and promote the exact commit-bound CI wheel instead of
  retesting and rebuilding a different artifact.
- Reworked both READMEs and bilingual architecture diagrams around conditional
  evidence budgets, fresh-only Gate decisions, planning-only history and the
  asymmetric human Adoption boundary.

## 1.10.0 — 2026-07-14

- Added explicit lossless Trace reuse with `aet trace --reuse-if-fresh`. Reuse
  never executes or falls back to execution and requires an exact non-secret
  argv digest, safe rendered argv, proof binding, declared-artifact set and bytes,
  stdout/stderr log bytes, successful source status, and current full Git
  workspace snapshot. Any argv redaction disables reuse rather than persisting a
  guessable secret digest. Canonical Trace JSON is protected by an adjacent
  integrity seal; validator FAIL/UNKNOWN is propagated into the Trace summary,
  Run Gate, and reuse decision. Missing legacy fields, tampering, or drift fail closed.
- Added `aet evidence receipt`, a compact hash-bound index for canonical Audit,
  Review, Trace, and Evidence Pack JSON. Canonical evidence remains unchanged;
  Agents can consume the receipt without loading full findings or embedded
  artifacts into context. Receipts independently recompute live workspace
  freshness and cannot overwrite their canonical source.
- Removed redundant in-request snapshot work from Trace and Run initialization,
  and made identical Run artifact attachments idempotent. Persistent snapshot
  caching remains intentionally absent because it cannot prove untracked-file
  freshness without rereading content.
- Generalized release evidence directories and candidate identifiers from the
  source version, removing v1.9 workflow and manifest path hard-coding.
- Classified releases explicitly as `deterministic` or `governance-adoption`.
  Deterministic runtime/evidence releases record the Real Host Gate as
  `NOT_APPLICABLE`; only adoption releases that claim changed Agent behavior
  require the complete commit-bound paired Gate. The workflow rejects both a
  missing adoption Gate and an irrelevant Gate attached to a deterministic
  release, and publishes the disposition as `release-evidence.json`.
  Classification is a tracked, base-tag and Diff-digest-bound contract:
  behavior-sensitive paths require exact reviewed exceptions with deterministic
  proofs when a Gate is not applicable. Releases retain the contract,
  commit-bound verification, evidence disposition, and (for adoption) verified
  Gate manifest as durable assets. Adoption contracts bind structured claim IDs
  and covered Suite IDs to the exact Candidate SHA verified by that manifest.

- Made the portable Skill explicitly opt-in and default-off: installation no
  longer implies authorization for routine coding or review, activation is
  scoped to the current user-requested task, and real-host evaluation/evolution
  requires separate explicit intent. Added bilingual project-fit and cost
  guidance distinguishing removable orchestration overhead from the rollout
  and suite coverage required for adoption-grade statistical confidence.
- Reworked the English and Chinese project entrypoints around AET's current
  position as an evidence-driven control plane for Agent-engineered
  repositories. The new narrative leads with the verified v1.9 real-host Gate,
  makes the Evidence → Quality → bounded Evolution → human-authority model
  explicit, sharpens toolchain differentiation and trust boundaries, and
  replaces the previous Mermaid renders with bilingual, editable dark-console
  architecture diagrams. The diagrams now separate Evidence Pack inputs from
  independent provenance stores, Quality regression staging from governance
  asset adoption, and audit-rule-only Shadow from the general adoption path.

## 1.9.0 — 2026-07-14

- Added a deterministic Quality layer: `aet quality diagnose` maps structured
  failure phenomena to explicit owner, action, confidence, review route, and
  bounded repair surface without rewriting source status; `quality promote`
  stages confirmed badcases as canonical, validation-only Learn Task v2
  candidates with immutable diagnosis provenance and deduplicated support.
- Added Learn Task v2 contracts for fixture integrity, ordered tool calls,
  argument constraints, proof/artifact requirements, command and change
  budgets, and deterministic suite verification. Observed replay now reports
  repeated-run any-success, all-success, Wilson intervals, paired McNemar
  statistics, and explicit `INCONCLUSIVE` / `INFRASTRUCTURE_ERROR` states.
- Hardened observed execution by reporting scripted network isolation as
  `PARTIAL`, rejecting unsupported `enforced-deny` before execution, copying and
  hashing fixtures without following links or special files, and accepting
  Trace credit only through the injected `./.aet-rollout/bin/aet trace` path.
  Snapshot state is independently recomputed without self-referencing the Trace
  JSON, and declared artifacts/logs are bound to real workspace files by source
  hash, size, fixed log path, independent redaction, and freshness. Outer child
  argv, Trace argv, and the intent proof command must match exactly; proof
  evidence must be an array.
- Clarified the privacy boundary between private raw rollout material and
  Evidence Only exports, including explicit environment-name allowlists for
  real-host runners. Process adapters require both Task permission and the
  `inherit_home` switch for `HOME`; the scripted adapter uses only the Task
  allowlist. Environment inheritance never makes secret values public evidence.
- Added deterministic business-flow fixtures and separated core, validation,
  and held-out real-host proof suites. A manual Codex workflow can produce a
  commit-, version-, candidate-, task-, fixture-, and raw-gate-bound release
  artifact; the release workflow reconstructs and verifies it. The v1.9 tag was
  locally gated with authenticated Codex CLI 0.144.1: core, validation and
  held-out each produced 6/6 candidate successes, 0/6 baseline successes, zero
  infrastructure failures and exact paired p=0.03125.
- Pinned the release runner to `@openai/codex@0.144.1`; process runners now
  capture and cache the canonical `--version` output, bind runner name/version
  through raw manifests, observed replays, observed Gates, and release
  manifests, reject blank/unknown version probes, and reject mismatched release
  provenance.
- Reframed AET as an evidence-driven Agent engineering quality and control
  layer, refreshed the bilingual user guide and architecture, and documented
  what AET deliberately does not provide: general benchmarking, LLM-Judge-led
  scoring, automatic semantic RCA/clustering, automatic repair/adoption, or an
  online ticket and business-metrics platform.

## 1.8.0 — 2026-07-13

- Generalized Evidence-Gated Evolution from a Skill-only pipeline into six
  Constitution-bound targets: Skill, audit rule, audit profile, review policy,
  Trace validator, and triage policy. Legacy v1 Skill candidates are upgraded
  in memory; new candidates use a hash-bound Candidate IR v2.
- Added a non-executable declarative audit RulePack, rulepack identity in Audit
  reports, reproducible Audit Feedback, 30 core / 15 validation / 15 held-out /
  10 adversarial audit tasks, baseline/candidate fixture replay, and monotonic
  multi-dimensional Gates.
- Added Shadow Audit that never changes official findings or exit status.
  Audit-rule adoption additionally requires 20 shadow runs across five
  repository fingerprints and three dates, every new finding confirmed, and
  zero confirmed false positives.
- Added bounded audit profiles, monotonic review policies, built-in
  JUnit/SARIF/coverage/JSON Trace validators bound to fresh declared artifacts,
  and triage policies that can reorder but never hide or rewrite findings.
- Fixed fenced Markdown examples being interpreted as real local references,
  hardened rulepack path containment and atomic adoption, refreshed bilingual
  documentation, and removed the CI wheel-version hardcode.

## 1.7.0 — 2026-07-12

- Added isolated Scripted, Codex, and Claude Code host runners, normalized
  command/final-answer evidence, deterministic behavioral scoring, paired
  rollout statistics, feedback records, tournament selection, and explicit
  preliminary versus adoption-grade observed Gates.
- Kept static Skill-document replay as Gate 0 while separating it from observed
  Agent behavior and preserving stage-only Sleep and explicit human adoption.

## 1.6.0 — 2026-07-12

- Completed the Evidence-Gated Evolution Lab through Phase 6: deterministic
  `inspect`/`summarize`, Candidate and replay-task schemas, Evidence Only local
  cross-project collection, repository/date support counts, bounded rejection
  memory, a timeout-bound model adapter, and a local `SKILL_EVOLUTION` run
  history.
- Hardened replay and Gate behavior: replay operates on temporary copies;
  validation and held-out suites must be byte-disjoint; Gate reports a quality
  vector plus token, command-surface, and workflow-overuse limits; Gate, stage,
  and adopt are hash-bound to the exact Patch IR; and a static no-network Gate
  Viewer supports human review.
- Bounded `aet learn sleep` with candidate, replay, model-call, and wall-clock
  limits, production-target change detection, and a stage-only terminal action.
  It never schedules, adopts, commits, pushes, uploads, or reads transcripts.
- Rewrote English and Chinese README entrypoints around real user workflows and
  the actual architecture, including Hermes absorbed-Skill migration diagnosis.

## 1.5.0 — 2026-07-12

- Added **Evidence-Gated Evolution Lab** (`aet learn`): evidence-only harvest,
  deterministic failure-pattern mining, bounded rule or opt-in model Patch IR,
  isolated replay, immutable-contract/self-audit/held-out gates, stage, human
  adoption with a Decision Ledger entry, rejection memory, and a bounded local
  `sleep` cycle that can stage but never adopt, commit, push, or upload.
- Added the Phase 0 evolution boundary, named editable blocks in the canonical
  Skill, core/validation/held-out/adversarial evaluation fixtures, and a metric
  vector acceptance policy rather than a synthetic trust score.
- `aet audit` now preserves a stale Hermes Skill reference as a `FAIL` while
  detecting its local `.absorbed_into` marker and emitting the installed
  replacement path in JSON/SARIF/Markdown remediation. This fixes the practical
  failure mode where a stale Skill Index was actionable only as a missing file.
- Added regression coverage for the full rules proposal pipeline and the
  absorbed-Skill migration diagnostic.

## 1.4.0 — 2026-07-12

- Added repeatable `aet trace --artifact <relative-path>` for explicitly
  declared UTF-8 reports generated by a traced command, including pytest JUnit
  XML. AET redacts report content before persisting it and embeds the redacted
  artifact plus SHA-256 in the portable Evidence Pack.
- Trace rejects absolute/outside-workspace artifact declarations. A missing,
  non-regular, undecodable, or unredactable declared report is recorded as
  `UNKNOWN`; a successful command then returns a non-zero Trace exit without
  rewriting the child command's successful execution result. Such a Trace also
  cannot advance a Run to `PROVEN` or mark a bound proof as complete.
- Added regression coverage for redacted report capture, portable-pack
  inclusion, missing artifacts, and outside-workspace rejection. This closes
  the evidence gap found while tracing Invest-Vault's pytest delivery proof.
- Constrained optional pytest discovery to AET's first-party `tests/` directory
  so nested dogfood repositories are not accidentally collected into AET's
  own test report.

## 1.3.0 — 2026-07-12

- Added an optional, deterministic **Context Manifest**: `aet context discover`
  records discoverable local instructions and Skills with SHA-256 hashes;
  `record` adds local references and explicit read attestations; `verify`
  reports changed/missing assets and workspace freshness.
- Read declarations are deliberately stored as `agent_attestation` (L5), while
  discovery and hashes remain L1 local evidence. AET does not claim that a
  model saw, understood, or used a recorded asset.
- Added a local JSON **Decision Ledger**: `aet decision init`, `add`, `list`,
  `verify`, and `supersede` preserve decision state, source hashes, evidence
  state, and replacement history. It is source-backed project memory, not RAG
  or a generic Agent-memory subsystem.
- Added regression coverage for Context Manifest discovery/attestation/drift,
  Decision Ledger hash verification, and supersession; updated the portable
  Skill, bilingual README, package metadata, and wheel smoke target.

## 1.2.0 — 2026-07-12

- Added an optional, append-only **Run Manifest** (`aet run init`, `status`,
  `verify`, and `close`) that describes a delivery lifecycle without becoming
  a workflow engine. Existing `audit`, `review`, `trace`, and `evidence pack`
  commands remain independently usable and may opt in through `--run`.
- Added declared lifecycle states: `INTENT_BOUND`, `AUDITED`, `REVIEWED`,
  `PROVEN`, `PACKED`, `STALE`, and `CLOSED`. A Run records every transition
  and only closes a fresh, successfully packed evidence chain.
- Extended `workspace_snapshot` with tracked-worktree, intent, and config
  fingerprints. Snapshot binding now distinguishes `INTENT_CHANGED`,
  `CONFIG_CHANGED`, and `UNTRACKED_SET_CHANGED` from generic workspace or
  HEAD differences.
- Added regression coverage for the full Run lifecycle, persisted stale state,
  intent/config changes, and changes to the untracked file set.

## 1.1.0 — 2026-07-12

- Added a shared `workspace_snapshot` to audit, review, and Trace reports. It
  captures the Git HEAD plus deterministic tracked and untracked worktree
  digests without executing a declared proof command.
- Evidence Packs now compare every supplied artifact with the workspace at
  pack time through `snapshot_binding`: `EXACT_MATCH`,
  `HEAD_MATCH_WORKTREE_DIFFERS`, `HEAD_DIFFERS`, or explicit `UNKNOWN`.
  A stale snapshot is reported separately from proof success; a command that
  passed is never rewritten as though it did not run.
- Reworked the static Evidence Viewer around delivery state, proof binding,
  and snapshot binding before exposing the raw JSON.
- Added regression coverage for exact snapshot matches and changes made after
  a successful proof; refreshed the release workflow's wheel smoke target.

- Reframed the README as a bilingual product entrypoint with an architecture,
  quality boundary, quick-start flows, Repo Archaeologist guide, and audience
  guidance.
- Added a complete Simplified Chinese README, a contribution guide, a copyable
  intent example, and structured GitHub Issue forms.

## 1.0.0 — 2026-07-11

- Added scoped `aet.toml` audit policies with explicit exclusion reasons.
- Added Evidence IR metadata, proof-bound Trace records, pack consistency
  checks, and an offline static Evidence Pack viewer.
- Added transparent `aet triage`; it ranks work but never changes a finding's
  `PASS`/`FAIL`/`UNKNOWN` status.
- Added `aet evolve` (Repo Archaeologist): plan, collect, build, report, and
  query stages; local Git/docs work offline and GitHub export/API use is
  explicit and evidence-manifested.
- Added release governance, schemas, CI, a v1 Skill flow, regression fixtures,
  and release documentation.

## 0.3.0 — 2026-07-11

- Added opt-in redacted command Trace and portable Evidence Pack compilation.
