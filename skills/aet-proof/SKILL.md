---
name: aet-proof
description: Execute one explicit verification command and record a minimal hash-bound AET proof receipt. Use only when the user explicitly invokes /aet-proof or asks AET to prove a command ran.
---

# /aet-proof

Answer one question: did this exact verification command run on this workspace?

Run:

```bash
aet quick proof --output <proof.json> \
  [--relevant-path <path>] [--artifact <path>] -- <argv>
```

The user's explicit `/aet-proof` call authorizes writing the requested JSON
receipt. It does not authorize any other write. The host LLM may locate the
project's recommended command, smallest relevant test set, relevant paths, and
declared artifacts. The deterministic executor alone records argv, timestamps,
exit code, redacted log digests, Git/worktree binding, relevant file hashes,
environment binding, and artifacts.

Never describe an unexecuted or non-zero command as passed. Never reuse a
historical result as a new execution. State that a bounded test does not prove
the full test suite passed. Do not generate HTML, SVG, Viewer, or Evidence Pack.

Budget: command duration, at most one LLM call only when locating the command,
zero remote calls by default, and one receipt write.

For a Chinese `/aet-proof` request, explain the receipt in natural Simplified
Chinese while keeping code and required technical terms in English. Otherwise
use English.

Write the one receipt, report its scope, and stop. Do not run additional tests
or invoke Fresh unless the user explicitly requests them.
