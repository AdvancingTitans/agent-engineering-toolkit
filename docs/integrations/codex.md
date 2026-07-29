# Codex

Install the AET CLI, then copy or install the five Skill directories supported
by your Codex environment. Invoke only the Skill that answers the current
question: `/aet-check`, `/aet-scope`, `/aet-proof`, `/aet-fresh`, or
`/aet-plan`.

`/aet-proof` is the only daily Quick Skill that executes the explicit argv
after `--`. `/aet-plan` is read-only and stops at `PROPOSED`.

Codex may interpret the resulting JSON, but must not promote `UNKNOWN`,
Observed facts, or a proposed Plan into verified Evidence or release authority.
