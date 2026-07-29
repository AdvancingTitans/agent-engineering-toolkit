# Planner Protocol

Create one strict JSON object with `schema_version` equal to
`plan-candidate/1.0`. Do not wrap it in Markdown or add prose.

Every edit must have a unique `edit_id`, one of `REQUIRED`, `OPTIONAL`,
`INVESTIGATE`, or `DO_NOT_EDIT`, a canonical repository-relative path, intent,
expected change, rationale, reference arrays, dependencies, tests, risks, and
limitations.

Every `REQUIRED` edit needs at least one resolvable Evidence, Atlas, or current
Source reference. Use only reference IDs present in the Planning Context.
Do not add fields that change scope or policy. Keep every verification step
`PENDING`; a command is argv data, not permission to execute.

Use `BEST_EFFORT`, `PARTIAL`, or `UNKNOWN` unless all bounded-completeness
conditions are satisfied. Preserve unresolved conflicts, stale source,
counter-evidence, unknowns, unsupported languages, and omitted counts.

See [examples](examples.md) for the command boundary.

Minimal shape:

```json
{
  "schema_version": "plan-candidate/1.0",
  "request_id": "REQ-...",
  "summary": "Propose one bounded edit.",
  "coverage_claim": "BEST_EFFORT",
  "edit_items": [],
  "investigation_items": [],
  "verification_steps": [],
  "assumptions": [],
  "unresolved": []
}
```

An empty verification array deliberately produces `NEEDS_EVIDENCE`; do not add
a fake command merely to obtain READY.
