# Contract

The Host supplies reasoning. AET supplies deterministic context construction,
candidate validation, rendering, packaging, and read-only queries.

The workflow is:

```text
User Request
→ AET Planning Context
→ Host reads bounded current source
→ strict Host Plan Candidate
→ AET deterministic Validator
→ PROPOSED Evidence-Linked Plan
```

The Planner is not an Executor. It does not edit source, execute commands,
commit changes, or turn a proposal into Evidence.

The five Plan statuses are `READY_FOR_HUMAN_REVIEW`, `NEEDS_EVIDENCE`,
`PARTIAL`, `BLOCKED`, and `SUPERSEDED`. Verification remains `PENDING` until a
separate explicitly authorized Proof workflow records execution.
