# Planning v1 Schemas

Planning v1 adds six strict, versioned contracts without changing Portable
Evidence Bundle v1:

| Contract | Schema version | Purpose |
| --- | --- | --- |
| Planning Request | `planning-request/1.0` | Goal, acceptance, scope, identities, budgets |
| Planning Context | `planning-context/1.0` | Bounded Bundle, Atlas, current Source, constraints, gaps, omissions |
| Plan Candidate | `plan-candidate/1.0` | Strict Host-produced proposal before validation |
| Evidence-Linked Plan | `evidence-linked-plan/1.0` | Deterministically validated `PROPOSED` Plan |
| Plan Reference | `plan-reference/1.0` | Evidence, Atlas, Source, Policy, or Verification locator |
| Plan Manifest | `plan-manifest/1.0` | Package contents, identities, producer, SHA-256 integrity |

Files are installed under `share/aet/schemas/planning/`.

## Compatibility

Authoritative objects are strict: `additionalProperties: false`, explicit
Schema versions, canonical repository-relative POSIX paths, and fixed enums.
Unknown versions and fields fail closed. A future incompatible change requires
a new Schema version; Planning v1 does not alter Bundle or Atlas semantics.

Candidate JSON additionally rejects duplicate keys, non-finite numbers,
Markdown fences, free text, invalid UTF-8, more than 5 MB, and excessive item
counts.

## Identity and authority

Planning Request binds workspace identity and optional Bundle/Atlas identity.
Context must preserve the same workspace. Atlas identity must match its Bundle.
Plan and Manifest must agree on Plan ID, request, status, source identity, and
authority.

Every validated Plan and Manifest has `authority: PROPOSED`. Planning objects
are not Core Evidence, Proof, execution records, or release authority.

## Paths and references

Paths must be canonical repository-relative POSIX strings. Absolute paths,
`..`, `.`, empty components, backslashes, symlink escapes, protected paths,
and out-of-scope paths are rejected or block the Plan.

Every REQUIRED Edit Item must cite at least one resolvable Evidence, Atlas, or
current Source reference. Reference kinds must match their Candidate field.
Current Source references bind path, symbol/range when present, content hash,
workspace identity, and read status.

## Omissions and status

Planning Context always records `omitted.nodes`, `omitted.source_ranges`, and
`omitted.source_bytes`. Budget exhaustion is never silent. Omission makes the
Plan `PARTIAL` and prevents `BOUNDED_COMPLETE`.

Known conflict, counter-evidence, stale data, and `UNKNOWN` remain explicit.
Missing critical evidence yields `NEEDS_EVIDENCE`; integrity and policy
violations yield `BLOCKED`.
