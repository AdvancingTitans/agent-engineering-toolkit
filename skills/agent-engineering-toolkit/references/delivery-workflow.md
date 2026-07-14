# Delivery workflow

Use only after the user explicitly activates this AET surface.

```bash
aet audit . --strict --format json --output .aet/evidence/audit.json
aet review . --base main --format json --output .aet/evidence/review.json
aet trace --proof <id> --intent aet.intent.json --artifact <report> \
  --output .aet/evidence/trace.json -- <argv>
aet evidence pack --audit .aet/evidence/audit.json \
  --review .aet/evidence/review.json --trace .aet/evidence/trace.json \
  --output .aet/evidence/evidence-pack.json
```

Only Trace executes, and only argv after `--`. Audit and Review never run Proof
commands. Read every FAIL first and preserve UNKNOWN. `trace --reuse-if-fresh`
is explicit, exact and fail-closed; it never falls back to execution. Use
`evidence receipt` for a compact index, never as a replacement for canonical
Evidence. An optional Run Manifest records attachment order and freshness but
does not select or execute commands.
