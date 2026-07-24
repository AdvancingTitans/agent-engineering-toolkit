# Agent Engineering Toolkit

**Investigate AI coding changes without letting the model invent evidence.**

AET Quick answers three questions: did the change fit the task, did the
verification really run, and does that proof still apply? Deterministic tools
produce facts; a host LLM may investigate intent and counter-explanations;
AET validates references, permissions, strength, and budget.

```text
deterministic facts → bounded LLM investigation → grounding validation → human decision
```

## Install

```bash
uv tool install .
aet --version
```

## Use one Quick surface

```bash
aet quick check .
aet quick scope . --base main --intent aet.intent.json
aet quick proof --output .aet/proofs/unit.json \
  --relevant-path src/auth/session.py -- python -m pytest -q
aet quick fresh --proof .aet/proofs/unit.json
```

Each Quick command answers one question and stops. `/aet-scope` does not treat a
path mismatch as proof of overreach; the host investigates necessity and a
reasonable counter-hypothesis. `/aet-proof` writes one bounded JSON receipt.
`/aet-fresh` distinguishes exact, relevant-file, artifact, environment, and
unknown freshness.

## Use the smallest surface

| Question | Command |
| --- | --- |
| Are Agent instructions and Skills usable and honest about verification? | `aet quick check` |
| Does this diff fit the user's task? | `aet quick scope` |
| Did this exact verification run? | `aet quick proof` |
| Does recorded proof still apply? | `aet quick fresh` |

AET is opt-in and normally off. It does not replace your Agent, tests or CI, and
it never auto-chains Quick commands, auto-adopts, commits, pushes, or releases.
The legacy `audit`, `review`, `trace`, Evidence Pack, and AET Lab surfaces remain
available for 1.x compatibility.

The repository includes an opt-in, eight-scenario
[four-mode comparison](https://github.com/AdvancingTitans/agent-engineering-toolkit/tree/main/eval/quick-investigation)
that reports recall, false discovery proportion, tool calls, time, and Tokens without
turning them into a trust score. Human-review and understanding fields remain
`UNKNOWN` until a person explicitly annotates them.

- [Source and full documentation](https://github.com/AdvancingTitans/agent-engineering-toolkit)
- [60-second stale-proof case study](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/docs/case-studies/stale-proof.md)
- [Stability contract](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/docs/stability.md)
- [Security and retention boundaries](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/docs/security-and-retention.md)
- [Contributing](https://github.com/AdvancingTitans/agent-engineering-toolkit/blob/main/CONTRIBUTING.md)

Python 3.11+ · MIT License
