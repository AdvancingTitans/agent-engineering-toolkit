# Planner and Helper scenarios

Evidence-Guided Planner is a read-only localization and proposal surface. It is
not an Executor and does not replace AET's other bounded questions.

| Surface | Question | Input | Output | May execute? |
| --- | --- | --- | --- | --- |
| Planner | What bounded edits and tests should a human review? | Request, Bundle, optional Atlas, current Source, Host Candidate | Validated `PROPOSED` Plan | No |
| Helper | Why is this Edit Item present, and what references support it? | Validated Plan package | Deterministic show, explain, trace, gaps | No |
| Audit / `/aet-check` | Are Agent assets unsafe or unverifiable? | Repository Agent assets | Evidence-backed findings | No |
| Scope / `/aet-scope` | Does an existing diff fit the task? | Intent and diff | Change-group dispositions | No |
| Proof / `/aet-proof` | Did this exact command run now? | Explicit argv and bindings | Proof Receipt | Yes, only explicit argv |
| Freshness / `/aet-fresh` | Does an older Proof still apply? | Proof and current workspace | Freshness state | No |

## Use Planner

Use Planner before implementation when a Host needs a bounded file, symbol,
dependency, test, risk, and verification proposal. The Host builds Context,
reads only necessary current Source, returns strict Candidate JSON, and shows
only the validated Plan.

`READY_FOR_HUMAN_REVIEW` does not mean the change is correct or complete. It
means the bounded Candidate passed deterministic integrity, policy, identity,
reference, and coverage checks.

## Use Helper

Use Helper after a Plan package exists:

```bash
aet plan show PLAN
aet plan explain PLAN --edit EDIT-001
aet plan trace PLAN --path src/aet/parser.py
aet plan gaps PLAN
```

Helper cannot answer arbitrary follow-up questions or introduce new facts. It
only projects recorded Plan and Reference data.

## Use Scope, Proof, and Freshness after implementation

An external Agent may implement a human-reviewed Plan. Then:

1. `verification-handoff` maps its external diff and flags unplanned paths;
2. `/aet-scope` can assess whether the actual diff fits the intent;
3. `/aet-proof` may execute an explicitly authorized pending command;
4. `/aet-fresh` later checks whether that Proof still applies.

The existence of a diff proves none of these steps. Until Proof is explicitly
run, verification remains `UNKNOWN`.

## Evidence gaps

When a broad request exceeds Bundle or current Source support, a good result is
`NEEDS_EVIDENCE` with concrete investigation items. Do not create speculative
REQUIRED paths or a fake verification command to force READY.
