# Scope drift

Scope is not the same as file count. A legitimate task can require a source
change, a schema update, documentation, and focused tests across modules.

`aet quick scope` compares the current diff with a human-reviewed intent
contract:

```bash
aet quick scope . --base main --intent aet.intent.json --format json
```

It records each change group, supporting evidence, and a counter-explanation.
An unrelated refactor can be outside scope even when it is small; necessary
cross-module compatibility work can remain relevant even when it touches
several files.

AET does not silently expand `allowed_paths` or the changed-path budget. Update
the intent contract only after human review of the broader task.
