# AET v1.18 activation positioning

## Frozen launch story

**Category:** Proof-carrying workflows for coding agents.

**Hero:** Your coding agent says tests passed. AET proves which code was
actually tested.

AET binds test runs, changed files, artifacts, and agent claims into portable
evidence, then tells you when that proof no longer applies.

## Primary users

- Developers using Codex, Claude Code, Cursor, Copilot, OpenCode, or compatible
  Agent Skills.
- Maintainers reviewing AI-generated changes.
- Teams handing bounded evidence between Agents and human reviewers.

## Release freeze

v1.18 adds activation, conversion, distribution, community, and aggregate
measurement assets only. It does not add another evidence layer, Agent
runtime, model integration, trust score, or governance object. Core capability
remains frozen for 14 days around the release candidate except for demo,
installation, documentation, compatibility, or security blockers.

## Claim discipline

- One fixture and one run prove only the observed case.
- A passing command does not prove current applicability after relevant code
  changes.
- Missing evidence stays `UNKNOWN`; unavailable external state stays
  `UNAVAILABLE`, `BLOCKED`, or `DEFERRED_WITH_REASON`.
- AET does not replace tests or CI and does not grant merge or release
  authority.

## Non-goals

No SaaS, built-in LLM, API key, user telemetry, auto-edit, auto-commit, push,
merge, release, external posting, or aggregate trust score.
