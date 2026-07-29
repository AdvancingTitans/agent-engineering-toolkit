# Evidence-Grounded Improvement Layer

The Improvement Layer converts validated Portable Evidence Bundle records into
bounded engineering work. It is deterministic, local, and model-free. It does
not edit source code and it does not grant recommendations evidence authority.

## Architecture

The authority order is fixed:

```text
Evidence
↓
Finding
↓
Improvement Issue
↓
Improvement Constraint
↓
Improvement Candidate
↓
Verification Contract
↓
Improvement Outcome
```

Portable Evidence Bundle v1 has no independent Finding collection. The adapter
therefore consumes validated portable Claims as Finding-compatible records
without changing either schema. Supported categories are:

- `scope_violation`
- `unsupported_claim`
- `missing_verification`
- `stale_verification`
- `missing_test`
- `error_handling_gap`
- `unknown_root_cause`

The deterministic analyzer normalizes, aggregates, de-duplicates, limits output
to five Items, and assigns priorities from `P0_BLOCKING` through
`P3_OPPORTUNITY`. It never produces a combined trust score.

For an unsupported Claim, grounding includes both `evidence_refs` and
`counter_evidence_refs`. This is important: the failure that contradicts a
Claim must remain available to the human report and Agent task instead of being
lost merely because it is not listed as positive support.

## Authority boundaries

Evidence records facts. A Finding records a bounded problem judgment. A
Constraint records required and forbidden behavior. A Candidate is always
`PROPOSED`; it cannot create Evidence, modify a Finding, enlarge Scope, or
remove an UNKNOWN. An Outcome becomes `verified_improvement` only when an
actual changed-path record, a matching Verification Contract, and current
passing Proof are all present.

When root cause is `unknown`, the generated Constraint is
`INVESTIGATION_REQUIRED` and direct code targets are rejected. Missing Evidence
is `INVALID_IMPROVEMENT_INPUT`; missing verification is `NOT_ACTIONABLE`;
unapproved scope expansion is `SCOPE_VIOLATION` or `NEEDS_HUMAN_REVIEW`;
missing references are `INVALID_REFERENCE`; stale Proof is `STALE_PROOF`.

Protected paths are:

```text
tests/evals/**
eval/**
grader/**
fixtures/**
.aet/**
```

Test deletion, grader changes, threshold lowering, fixture-truth changes, and
failure hiding produce `ANTI_GAMING_FAILURE`.

## CLI

Validate that a Bundle can be consumed:

```bash
aet improvement doctor path/to/bundle
```

Generate deterministic state and `human-report.md` under
`.aet/improvements/`:

```bash
aet improve path/to/bundle
```

Generate a bounded coding-Agent task:

```bash
aet improve prompt IMP-001
```

Validate a Candidate and, when valid, write `candidate.json`,
`candidate-validation.json`, and `verification-contract.json`:

```bash
aet improve validate candidate.json
```

Supply a contract-bound `.aet/improvements/proof.json`, then verify:

```bash
aet improve verify IMP-001
```

For deterministic metric comparison, provide `before.json` and `after.json`:

```bash
aet improve compare
```

## Candidate example

```json
{
  "id": "CAND-001",
  "constraint_id": "IC-001",
  "strategy": "Introduce a structured empty-result state.",
  "targets": [
    {
      "path": "src/tool/result.py",
      "symbol": "normalize_result"
    }
  ],
  "assumptions": [],
  "risks": [],
  "verification_plan": ["python -m unittest tests.test_tool"],
  "finding_refs": ["claim-001"],
  "evidence_refs": ["ev-001"],
  "claim_refs": ["claim-001"],
  "deleted_paths": [],
  "human_approval_required": false,
  "root_cause_status": "evidenced"
}
```

## Lifecycle

Candidate validation checks schema, Evidence/Finding/Claim grounding, allowed
Scope, protected paths, local file and symbol references, conclusion strength,
and anti-gaming rules. Validation success still means only `PROPOSED`.

Verification binds the Candidate ID, Contract ID, commands, exit results,
relevant changed paths, and Freshness. Before/After comparison preserves
`PASS`, `FAIL`, `UNKNOWN`, and `NOT_APPLICABLE`; it does not manufacture a
score. A regression leaves the Outcome `implemented_unverified`.

Evidence Atlas adds the fixed `improvement-chain` and `regression-lineage`
Perspectives. Portable Evidence Bundle v1 does not carry independent
Improvement records, so those Perspectives explicitly remain `UNKNOWN` until
source-bound records exist; the Atlas never infers Candidate or Outcome state
from recommendation text.

## Reproducible project-review case

[`examples/evidence-grounded-improvement`](../examples/evidence-grounded-improvement/README.md)
runs a checked-in failing regression against a deliberately flawed empty-result
adapter. It records `ev-empty-result-regression`, derives `IMP-001`, limits
changes to one sample file, names the exact verification command, and builds
Claim Chain plus Improvement Chain views from the same Bundle. The tracked
human report, Agent task, JSON records, and Mermaid projections are the actual
outputs used in the README—not hand-written success examples.
