# AET vs Plan Mode

Plan Mode helps a coding Agent reason about what to change before editing. AET
does not replace that judgment.

AET can provide a bounded Planning Context, validate source locations and
Evidence references, and package a read-only `PROPOSED` Plan. The host Planner
still supplies engineering judgment; a human still authorizes implementation.

An AET Plan never edits source or executes verification. After external
implementation, Proof remains `UNKNOWN` or `PENDING` until an explicit command
runs and is bound to the resulting workspace.
