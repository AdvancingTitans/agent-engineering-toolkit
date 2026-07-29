# Evidence-grounded improvement case

This example contains a deliberately flawed tool-result adapter. An empty tool
result becomes the factual sentence “No security issues were found.” The
checked-in regression test rejects that behavior.

Run the complete case from the repository root:

```bash
uv run python examples/evidence-grounded-improvement/build_example.py \
  --output .aet/evidence/empty-result-review
uv run aet improvement doctor .aet/evidence/empty-result-review
uv run aet improve .aet/evidence/empty-result-review
uv run aet improve prompt IMP-001
uv run aet atlas build .aet/evidence/empty-result-review \
  --perspectives claim-chain,conflicts,improvement-chain --no-llm
```

The Improvement report and Agent task are derived from the Bundle's
`claim-empty-result-is-grounded` and `ev-empty-result-regression` references.
The Evidence Atlas is a separate deterministic projection of the same Bundle.
The prompt never becomes Evidence, and the `improvement-chain` Perspective
remains `UNKNOWN` because Portable Evidence Bundle v1 contains no independent
Improvement records.
