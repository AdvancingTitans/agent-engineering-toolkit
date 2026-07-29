# Examples

Build context:

```bash
aet plan context \
  --workspace . \
  --request request.md \
  --bundle .aet/evidence/review \
  --output planning-context.json
```

Validate the strict Host response:

```bash
aet plan validate-candidate \
  --context planning-context.json \
  --candidate plan-candidate.json \
  --output .aet/plans/PLAN-001
```

Inspect the validated result:

```bash
aet plan show .aet/plans/PLAN-001
aet plan gaps .aet/plans/PLAN-001
```

If required evidence is absent, return explicit investigation items and allow
the validated status to remain `NEEDS_EVIDENCE`; do not guess missing edit
locations.

## Single-file fix

Use one REQUIRED implementation path plus its focused test when current Source
and Evidence both bind the failure to that file. Keep coverage
`BEST_EFFORT`; the test command remains `PENDING`.

## Cross-module behavior

Create separate, dependent Edit Items for the entrypoint, core implementation,
Schema or serialization surface, compatibility layer, and tests. Cite the
specific Evidence or Source reference for each item; do not list every shared
module “for safety.”

## Insufficient evidence

For a request such as “refactor every permission check” when the Bundle covers
only one adapter, return no guessed REQUIRED edits. Record investigation items
for permission entrypoints, callers, protected paths, and focused tests. Leave
verification absent until it can be bound, so validation returns
`NEEDS_EVIDENCE`.
