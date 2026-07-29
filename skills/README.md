# AET Skills

Install the repository's portable Skills with:

```bash
npx skills add AdvancingTitans/agent-engineering-toolkit
```

The skills.sh CLI reports anonymous installation statistics. To opt out:

```bash
DISABLE_TELEMETRY=1 npx skills add AdvancingTitans/agent-engineering-toolkit
```

That telemetry belongs to skills.sh. AET itself adds no telemetry.

| Skill | Primary question | Executes command? | Writes? | Default network | Authority |
| --- | --- | --- | --- | --- | --- |
| `aet-check` | Are Agent instructions usable and verifiable? | No project code | No | None | Read-only finding |
| `aet-scope` | Does each change group fit the authorized task? | At most one authorized discriminating test | No source writes | Up to two authorized reads | Investigated disposition |
| `aet-proof` | Did this exact command run on this workspace? | Yes, explicit argv only | One requested receipt | None | Bounded Proof |
| `aet-fresh` | Does historical Proof still apply? | No project command | No | None | Deterministic freshness |
| `aet-plan` | What should change without editing yet? | No verification | Plan package only | None by default | `PROPOSED` only |

Install or load only the Skill that answers the current question. Native Skill
hosts use each folder directly. Other hosts may load the corresponding
`SKILL.md` as instructions and invoke the same local CLI.
