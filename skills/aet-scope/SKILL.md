---
name: aet-scope
description: Investigate whether an AI coding change matches the user's task and whether cross-module changes are necessary. Use only for an explicit /aet-scope request.
---

# /aet-scope

Answer one question: does each change group fit the user's authorized task?

## Boundary

Run `aet quick scope <root> --base <revision> --intent <intent.json>
--format json` for the deterministic preflight. Recover intent in this order:
current request, later authorization, explicit Intent, Issue/PR, Commit
message, then clearly marked inference.

A path outside a declared surface is only a fact that triggers investigation.
It is never sufficient by itself for `OUT_OF_SCOPE`.

## Investigation

Group changes by purpose. For each material group, examine direct dependencies,
shared infrastructure, interface migration, tests, generated files, later
authorization, and a reasonable counter-hypothesis. Store each useful tool
step in an Investigation Ledger with its question, immutable result reference,
observation, hypothesis effect, decision value, and cost.

Allowed dispositions are `IN_SCOPE`, `JUSTIFIED_EXPANSION`,
`POSSIBLE_SCOPE_EXPANSION`, `OUT_OF_SCOPE`, and `INSUFFICIENT_INTENT`.

Before rendering an Investigated Finding, pass the canonical Finding, Ledger,
authorized-tool set, and Investigation Contract through
`aet.investigation.validate_investigated_finding`. If that API is unavailable
or rejects the record, preserve `HYPOTHESIS`/`UNKNOWN` and disclose why.

Budget: 45 seconds, four rounds, two LLM calls, eight tool calls, two authorized
remote reads, one expensive call, and at most one low-cost discriminating test.
No code writes.

For a Chinese `/aet-scope` request, use natural Simplified Chinese while
keeping code and required technical terms in English. Otherwise use English.

Report facts, judgment, counter-explanation, uncertainty, location, and the
smallest next action, then stop. Do not repair, prove, publish, or enter Lab.
