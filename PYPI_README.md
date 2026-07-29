# Agent Engineering Toolkit

> **Your coding agent says tests passed. AET proves which code was actually tested.**

AET provides proof-carrying workflows for coding agents. It binds test runs,
changed files, artifacts, and agent claims into portable evidence, then tells
you when that proof no longer applies.

## Try the stale-proof demo

After v1.18.0 is published:

```bash
uvx --from agent-engineering-toolkit aet demo stale-proof
```

Expected result:

```text
1. Test command executed                    PASS
2. Proof matches the tested source          EXACT_MATCH
3. Source changed without rerunning tests   RELEVANT_FILES_CHANGED

Demo result: PASS
```

The test really passed. Then a relevant source file changed without rerunning
it, so AET correctly stopped applying the old proof to the current code.

The demo is local and deterministic after package download. It uses Git and
Python's standard-library `unittest`; it makes zero network or LLM calls.

## Install

```bash
uv tool install agent-engineering-toolkit
aet --version
```

The PyPI package currently remains at v1.11.1. Do not advertise the v1.18 demo
command until PyPI or the exact GitHub Release wheel is verified.

## Choose the smallest surface

| Question | Command |
| --- | --- |
| Are Agent instructions usable? | `aet quick check .` |
| Does a diff fit the task? | `aet quick scope . --base main --intent aet.intent.json` |
| Did this command run on these files? | `aet quick proof --output proof.json --relevant-path src/app.py -- <argv>` |
| Does old proof still apply? | `aet quick fresh --proof proof.json` |
| What should change without editing? | `aet plan context ...` |

AET is not another coding agent. It does not replace tests or CI, turn missing
evidence into `PASS`, or auto-edit, commit, push, merge, or release.

- [Source and documentation](https://github.com/AdvancingTitans/agent-engineering-toolkit)
- [Five-minute start](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/docs/start-here.md)
- [Status and authority](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/docs/reference/status-and-authority.md)
- [Security](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/SECURITY.md)

Python 3.11+ · MIT License · no product telemetry
