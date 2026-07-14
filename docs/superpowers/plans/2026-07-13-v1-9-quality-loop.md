# AET v1.9.0 evidence-to-quality implementation plan

> Historical v1.9 implementation record. Its universal fresh-Gate release rule
> is superseded by the diff-bound release classification policy in the current
> README; this document is not an active release contract.

## Decision

Build the smallest quality loop that follows AET's existing evidence boundary:

`evidence facts -> deterministic evaluator -> failure pattern -> bounded candidate -> replay and Gate -> human adoption`

Do not build a generic Agent benchmark, LLM Judge center, conversation-quality platform, guessed root-cause engine, mutable Skill-owned evaluator, or automatic adoption/push system.

## Pre-flight gates

- Baseline `aet audit --strict` must pass and its JSON must be retained.
- Baseline tests must execute through `aet trace`; missing test dependencies are infrastructure failures, not product failures.
- Parallel implementation tasks may not overlap production files. Task 2 starts only after Task 1 passes review because both touch `learn.py`.
- Every behavior change follows RED -> GREEN -> full regression.

## Task 1 — Normalize evidence into Experience records

Modify `src/aet/learn.py` and `tests/test_learn.py`.

- Add allowlisted adapters for `evidence_pack`, `aet_run`, `learning_observed_replay`, `learning_observed_score`, and `audit_feedback`; do not recursively mine arbitrary JSON.
- Preserve FAIL and UNKNOWN from nested components, attach parent/component evidence references, and deduplicate repeated child reports.
- Carry task, runner, variant, iteration, fixture/repository fingerprint, and observed time without exporting transcript, response, events, environment, or logs.
- Preserve compatibility with existing `learning_experiences` packs and the current top-level experience ID behavior.
- Enrich newly written observed scoring records with the same context.

Revision gate: nested FAIL/UNKNOWN, PASS-only, duplicate, old-pack, feedback-context, observed-context, and secret-retention tests must pass.

## Task 2 — Make scorer and external evaluator contracts fail closed

Modify `src/aet/learn_scoring.py`, `src/aet/learn_statistics.py`, `src/aet/learn.py`, `schemas/learn-task-v2.schema.json`, `schemas/learn-candidate.schema.json`, and focused tests.

- Consume each task's declared hard requirements and reject unknown requirement codes.
- Define a versioned mapping from external lower-case requirements (`no_scope_violation`, `no_unsupported_success_claim`, `fresh_trace_required`, plus the budget/surface/workflow requirements) to scorer finding codes. Unknown requirements fail during suite verification, before a runner starts.
- Treat every declared hard failure as rollout failure, including surface, workflow, command-budget, and changed-file-budget violations.
- Add external Task v2 `expected_behavior.required_tool_calls` constraints for ordered tool names and exact/subset JSON arguments; score structured `tool_call` events deterministically so a correct final answer with a missing, reordered, or malformed call fails.
- Validate Learn Task v2 policy, expected behavior, runner, budgets, network policy, scoring keys, and types with stdlib code before execution.
- Fail closed when a task requires enforced network isolation but the selected runner cannot provide it.
- Deprecate `learn-candidate.schema.json` by making it reference the canonical `evolution-candidate-v2.schema.json`; do not create a second v2 definition. Add contract tests for every registered target family.
- Add exact paired-statistics boundary tests. For each task×variant group with `N > 0`, report successes/N, any-success (`successes > 0`), all-success (`successes == N`), and a 95% Wilson interval. An empty group is `UNKNOWN`, never 0% or PASS. Keep the paired release Gate on exact McNemar; reliability metrics never replace hard Gates.

Revision gate: policy bypass, unknown hard requirement, schema looseness, network capability, 0/5, 5/5, 6/6, regression, and infrastructure cases must pass.

## Task 3 — Add bounded quality assets, not generic RCA

Create the minimum cohesive implementation in `src/aet/quality.py`, wire `aet quality diagnose` and `aet quality promote` in `src/aet/cli.py`, add `schemas/quality-diagnosis-v1.schema.json`, and test in `tests/test_quality_loop.py`.

- `diagnose` consumes an Evidence Only experience/pattern plus an explicit local policy and writes `quality-diagnosis/v1`: phenomenon code, evidence refs, candidate repair surface, confidence, review route, owner/action only when explicitly mapped by that versioned policy. `rule_conflict`, `new_schema`, `confirmed`, `reproducible`, and `deidentified` are explicit typed input/policy facts, never model inferences.
- Support review routing for high risk, low confidence, rule conflict, and new schema; routing never changes PASS/FAIL/UNKNOWN.
- `promote` consumes `quality-diagnosis/v1` plus explicit expected behavior and writes a staged Learn Task v2 validation candidate. Only `validation` is accepted; automatic writes to core, held-out, and adversarial are rejected.
- Deduplicate by canonical content hash, choose representative evidence, record first/last seen and support, and never write held-out/core sets automatically.
- Promotion stages a candidate for human review; it never adopts, edits a Skill, commits, or pushes.

Revision gate: ambiguous, unconfirmed, non-reproducible, non-de-identified, duplicate, and held-out-target cases must fail closed; valid candidates must be deterministic.

## Task 4 — Fresh business validation and CI gates

Modify `eval/real-agent/**`, `.github/workflows/ci.yml`, `.github/workflows/release.yml`, and examples only after the APIs stabilize.

- Add deterministic business cases for required tool order/arguments, tool failure without false success, correct final text with an invalid process, stale Trace, and bounded workspace writes.
- Repeat paired cases enough to exercise the exact-statistics boundary; report any/all success and confidence interval.
- Keep credentialed real Codex/Claude runs manual or scheduled, but require a commit/version-bound fresh gate before Release.
- CI must run contract/schema verification, deterministic business flows, full tests, strict Audit, build, and wheel smoke.
- Fix install examples so they do not depend on an unpublished PyPI package.

Pre-flight gate for release: the Intent's `real-host-gate` command must produce adoptable Codex statistics and a gate artifact whose provenance binds the release commit, candidate hash, suite hashes, and runner. Offline re-scoring of an old rollout is not accepted.

## Task 5 — Documentation, version, and release

Update version metadata, Skill contract, README, Chinese README, architecture diagrams/source, boundary/security docs, CHANGELOG, and release notes.

- Position AET as a local evidence and bounded asset-governance layer outside the Agent runtime critical path.
- Explain what AET verifies, what remains UNKNOWN, where it sits relative to Agent runtimes, observability/eval tools, CI, and Skill optimizers.
- Distinguish repository archaeology from Agent execution diagnosis.
- Document deterministic quality assets and real boundaries without calling them universal RCA or automatic learning.
- Run each declared proof through its own Trace and compile one Evidence Pack per proof because a Pack intentionally carries one Trace. Build `.aet/evidence/v1.9-release-index.json` containing hashes/statuses for all proof packs, final Audit, final Review, independent spec/quality verdicts, remote CI URL/SHA/status, release commit, and version. Perform independent review, push, wait for CI, then publish v1.9.0.

Abort gate: do not publish if tests, business evidence, Audit, Review, build, wheel smoke, independent review, or remote CI is not PASS.
