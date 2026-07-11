# Agent Engineering Toolkit

Evidence-first static audits for coding-agent context and Skills.

`aet` checks the files that steer coding agents — such as `AGENTS.md`,
`CLAUDE.md`, `SKILL.md`, references, and local command paths — before an agent
starts work. It is read-only, deterministic, and does not require an API key or
an LLM.

```bash
uv tool install agent-engineering-toolkit
aet audit .
aet audit . --format sarif --output aet.sarif --strict
```

## What v0.1 checks

- Broken Markdown links and explicit local command targets.
- Oversized root instruction files and duplicated directives.
- Skill frontmatter, directory/name consistency, referenced local files, and a
  verification step.

Each finding carries a rule ID, file/line evidence, severity, remediation, and
rule version. The report uses `PASS`, `FAIL`, `UNKNOWN`, and
`NOT_APPLICABLE`; it intentionally does not hide uncertainty behind a single
score.

## Output formats and exit codes

`--format markdown` is the default. `json` is for agents and automation, and
`sarif` is for code-scanning systems.

- Default exit code is non-zero when a `FAIL` finding is emitted.
- `--strict` is additionally non-zero for `WARN` findings.

## Scope

v0.1 audits context and Skills only. Intent-to-diff review is the next release.
Repo Archaeologist is retained as a future, separate `aet evolve` capability;
it is deliberately not part of the static core.

See [PROJECT_MEMORY.md](PROJECT_MEMORY.md) for decisions, phase results, and
rollback points.
