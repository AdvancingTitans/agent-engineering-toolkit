# AET Evidence Action template

This directory is source material for a separate
`AdvancingTitans/aet-evidence-action` repository. Do not publish it from the
main AET repository.

```yaml
permissions:
  contents: read

steps:
  - uses: actions/checkout@v4
  - uses: AdvancingTitans/aet-evidence-action@v1
    with:
      mode: check
      version: 1.19.1
      path: .
```

Security-sensitive workflows should pin the Action commit SHA. The `version`
input must be exact; examples never install floating `latest`.

Supported modes:

- `check`: read-only Agent instruction/Skill preflight;
- `scope`: read-only diff and intent investigation;
- `fresh`: read-only comparison with an existing proof.

`proof` is intentionally rejected. Executing an arbitrary command from an
untrusted fork can expose secrets or mutate the runner. Run proof only as an
explicit CLI step in a workflow and repository you control.

Outputs are `authoritative-status`, `freshness-state`, and `report-path`.
Inputs are passed as argv elements; the script never uses `eval`.
