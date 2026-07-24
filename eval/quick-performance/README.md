# AET Quick local performance evidence

This AET Lab Harness records raw local samples for the Quick acceptance budgets.
It adds no Quick command and makes no model-service or cross-repository claim.

```bash
python eval/quick-performance/runner.py \
  --root . \
  --base v1.12.0 \
  --intent aet.intent.json \
  --repetitions 30 \
  --output eval/quick-performance/results/v1.13.0.json
```

The report retains every `time.perf_counter` sample, uses nearest-rank P95, and
records Python, platform, architecture, tracked-file count, changed-file count,
and the exact base. Check and Scope use this repository; Fresh uses a minimal
temporary Git fixture with an exact proof.
