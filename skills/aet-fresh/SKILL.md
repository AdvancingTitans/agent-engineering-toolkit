---
name: aet-fresh
description: Deterministically check whether an AET proof still applies to the current workspace. Use only for an explicit /aet-fresh request.
---

# /aet-fresh

Answer one question: does this historical proof still apply to the current
workspace?

Run:

```bash
aet quick fresh --proof <proof.json> --format json
```

The CLI alone compares Git HEAD, workspace state, declared relevant files,
artifacts, runtime identity, and dependency lockfiles. The host LLM may explain
impact and the smallest rerun, but it cannot change the deterministic state.

States are `EXACT_MATCH`, `RELEVANT_FILES_MATCH`,
`HEAD_CHANGED_RELEVANT_FILES_MATCH`, `RELEVANT_FILES_CHANGED`,
`ARTIFACT_CHANGED`, `ENVIRONMENT_CHANGED`, and `UNKNOWN`.

Budget: three seconds, zero LLM calls by default, zero network calls, and zero
writes. An explicit explanation may use one host LLM call after the
deterministic result exists.

For a Chinese `/aet-fresh` request, explain the result in natural Simplified
Chinese while keeping code and required technical terms in English. Otherwise
use English.

Report what changed and the minimum proof to rerun, then stop. Never rerun it
automatically.
