# Agent Engineering Toolkit

**Stop coding Agents from claiming “tests passed” without verifiable proof.**

AET is a local CLI that records exact command execution, declared artifacts,
human intent and the Git workspace snapshot. It can then check whether that
evidence still matches the current code before a handoff or release.

```text
Agent claim → exact execution evidence → live freshness check → human decision
```

## Install

```bash
uv tool install agent-engineering-toolkit
aet --version
```

## Record one proof

Declare the expected proof in `aet.intent.json`, then run the exact command
through Trace:

```bash
aet trace --proof unit-tests --intent aet.intent.json \
  --artifact reports/pytest.txt \
  --output .aet/evidence/trace.json \
  -- python -m pytest -q

aet evidence receipt --report .aet/evidence/trace.json
```

If the workspace changes after the test, the historical command remains a
success while current freshness becomes `FAIL`. Missing evidence remains
`UNKNOWN`; AET never markets it as a pass.

## Use the smallest surface

| Question | Command |
| --- | --- |
| Are Agent instructions and Skills structurally usable? | `aet audit . --strict` |
| Is a diff inside the approved change contract? | `aet review . --base main --intent aet.intent.json` |
| Did this exact command produce this artifact? | `aet trace … -- <argv>` |
| Does recorded proof still match the workspace? | `aet evidence receipt --report <trace.json>` |

AET is opt-in and normally off. It does not replace your Agent, tests or CI, and
it never auto-adopts, commits, pushes or releases a governance candidate.

- [Source and full documentation](https://github.com/AdvancingTitans/agent-engineering-toolkit)
- [60-second stale-proof case study](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/docs/case-studies/stale-proof.md)
- [Stability contract](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/docs/stability.md)
- [Security and retention boundaries](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/docs/security-and-retention.md)
- [Contributing](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/CONTRIBUTING.md)

Python 3.11+ · MIT License
