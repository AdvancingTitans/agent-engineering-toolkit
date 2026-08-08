# Behavioural risk diagnosis example

Normalize a native run first, then diagnose it with an explicit Intent v2 contract and a reviewed risk policy:

```bash
aet run normalize \
  --source codex \
  --input native-run.jsonl \
  --output .aet/normalized-run

aet risk diagnose \
  --run .aet/normalized-run \
  --intent aet.intent-v2.json \
  --policy examples/risk/risk-policy.json \
  --json-out .aet/risk-diagnosis.json \
  --md-out .aet/risk-diagnosis.md
```

`FAIL` means a bounded risk condition was positively observed. `PASS` requires complete declared coverage. Missing or conflicting evidence is `UNKNOWN`; policy-declared exclusions are `NOT_APPLICABLE`.

The report does not infer a stable model motive, produce a holistic score, call a model API, or execute an intervention. A human or the Agent Host must inspect the cited records before acting on any `PROPOSED` recommendation.
