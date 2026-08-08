# Agent Engineering Toolkit

> **A coding Agent can say “done.” AET shows what happened, what was proved,
> what changed, and what must remain `UNKNOWN`.**

AET is a local Evidence Plane for coding Agents. It binds Git state, exact
command execution, artifacts, Agent runs, and review constraints into portable,
hash-bound evidence. It does not replace tests or CI, invent missing facts, or
auto-edit, commit, push, merge, release, or execute an intervention.

## Install

The PyPI package currently exposes the v1.18.0 feature set:

```bash
uv tool install agent-engineering-toolkit
```

For the current v1.19.1 feature set, install the exact GitHub Release wheel:

```bash
uv tool install https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/download/v1.19.1/agent_engineering_toolkit-1.19.1-py3-none-any.whl
```

## Smallest useful surfaces

| Question | Command |
| --- | --- |
| Are Agent instructions usable? | `aet quick check .` |
| Is a diff inside approved intent? | `aet quick scope . --base main --intent aet.intent.json` |
| Did exact argv run on declared files? | `aet quick proof ... -- <argv>` |
| Does recorded proof still apply? | `aet quick fresh --proof proof.json` |
| What should change without editing? | `aet plan context ...` |
| What is the bounded review context? | `aet review-graph open <package>` |

Advanced surfaces include Portable Evidence Bundles, Evidence Atlas, graph-first
review handoffs, Evidence-Guided Plans, deterministic Behavioural Risk
Diagnosis, repository archaeology, and gated local evolution. Authoritative
states remain `PASS`, `FAIL`, `UNKNOWN`, and `NOT_APPLICABLE`; advice remains
`PROPOSED`.

- [Source and full documentation](https://github.com/AdvancingTitans/agent-engineering-toolkit)
- [Five-minute start](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/docs/start-here.md)
- [Status and authority](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/docs/reference/status-and-authority.md)
- [Security](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/SECURITY.md)

Python 3.11+ · MIT License · no AET product telemetry
