# Stability contract

AET 1.x treats evidence semantics as a compatibility boundary, not merely its
Python API or CLI spelling.

## Stable in 1.x

- Existing top-level commands will not silently change from read-only to
  executing commands, accessing a network, or writing production assets.
- `UNKNOWN` will not be reclassified as `PASS` for compatibility or convenience.
- Trace execution status and current-workspace freshness remain separate facts.
- Candidate generation, evaluation and human adoption remain separate authority
  boundaries; no 1.x update will auto-adopt, commit, push or release a candidate.
- Published JSON records retain `schema_version` and `report_kind`. Additive
  fields may appear in a minor release; removing or redefining a field requires
  a new schema version.
- AET remains opt-in. Installation alone never authorizes an Agent to run it.

## Versioning policy

- **Patch:** correctness, documentation or packaging fixes that preserve public
  evidence semantics.
- **Minor:** additive commands, fields, rules or target adapters.
- **Major:** removal, incompatible CLI changes, or a changed trust/authority
  boundary.

Deprecated behavior is documented in the changelog for at least one minor
release before removal. Security fixes may fail closed immediately when keeping
the old behavior could accept invalid evidence.

## Release cadence

Releases are claim-driven rather than commit-driven. Routine work is accumulated
and released no more than weekly unless a security or evidence-integrity defect
requires an earlier patch. Every release is built once in CI and the exact
verified artifact is promoted to distribution channels.

The detailed machine contracts remain in `schemas/` and the versioned Skill
references. This document states the compatibility promise a user can rely on.
