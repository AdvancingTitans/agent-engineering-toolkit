# Repository Audit Showcase

Use this surface only when the user explicitly requests one of the three
commit-locked public repository cases:

```bash
aet audit swe-agent --repo /path/to/SWE-agent
aet audit google-adk --repo /path/to/adk-python
aet audit openhands --repo /path/to/OpenHands
```

The checkout must match the commit in its built-in
`repository-audit-profile/v1`. AET reads only the bounded UTF-8 files, never
executes upstream code or tests, and writes two shared machine artifacts:

- `evidence_manifest.json`
- `findings.json`

The same five human-readable artifacts are rendered under both `en/` and
`zh-CN/`:

- `repository-summary.md`
- `audit-report.md`
- `audit-report.html`
- `diagrams/agent-flow.svg`
- `diagrams/evidence-chain.svg`

The 15-minute budget starts after the local checkout and AET installation
already exist. Clone time, dependency installation, LLM network time, and
manual review are excluded. LLM use is off and cannot create, delete, or
change a Finding.

Treat every result as an engineering observation. `UNKNOWN` remains unknown,
and `review.status=PENDING` means the report is not approved for publication.
Reports contain locations and hashes, never upstream source text. OpenHands
`enterprise/**` and `tests/**/enterprise/**` are prohibited from collection.
