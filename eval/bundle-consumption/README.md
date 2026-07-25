# Portable Bundle consumption evaluation

This deterministic harness evaluates one Portable Evidence Bundle and one
structured Review Result. It does not call an external Agent.

It reports ten independent metrics:

- citation correctness;
- Observation/Evidence distinction;
- counter-evidence retention;
- unknown preservation;
- freshness handling;
- unsupported conclusion rate;
- missing-evidence overreach rate;
- relevant Evidence recall;
- approximate context Tokens;
- measured time to first grounded conclusion.

Every metric uses `PASS`, `FAIL`, `UNKNOWN`, or `NOT_APPLICABLE`. The report
does not calculate an aggregate score or trust score.

Context Tokens use an explicit approximation: canonical JSON UTF-8 bytes for
the Bundle Index/Core plus Review Result, divided by four and rounded up.
Time-to-first-grounded-conclusion requires actual elapsed seconds in
`extensions.evaluation.conclusion_elapsed_seconds`; missing timing remains
`UNKNOWN`.

Run the tracked deterministic example:

```bash
python eval/bundle-consumption/runner.py \
  --bundle tests/fixtures/evidence-bundles/minimal \
  --review eval/bundle-consumption/fixtures/minimal-review.json \
  --expectations eval/bundle-consumption/fixtures/minimal-expectations.json \
  --scenario-id minimal-current-proof \
  --consumer-id local-structured-review \
  --output .aet/eval/minimal-current-proof.json
```

Run the ten-category planning suite without third-party outputs:

```bash
python eval/bundle-consumption/runner.py \
  --suite eval/investigation-quality/fixtures/scenarios.json \
  --output .aet/eval/planned-scenarios.json
```

Unavailable consumers remain `NOT_APPLICABLE`; the runner does not infer a
failure or success from missing third-party output.

Generate the ten deterministic synthetic Bundles and render one SDK-free
prompt for a measured consumer:

```bash
python eval/bundle-consumption/generate_fixtures.py \
  --output .aet/eval/bundle-consumption/generated
python eval/bundle-consumption/prepare_prompt.py \
  --catalog eval/investigation-quality/fixtures/scenarios.json \
  --bundle-root .aet/eval/bundle-consumption/generated
```

After an external consumer returns the documented `reviews` JSON envelope,
score all ten scenarios without aggregation:

```bash
python eval/bundle-consumption/score_collection.py \
  --catalog eval/investigation-quality/fixtures/scenarios.json \
  --bundle-root .aet/eval/bundle-consumption/generated \
  --response consumer-response.json \
  --consumer-id measured-consumer \
  --elapsed-seconds 12.5 \
  --output measured-report.json
```

The elapsed value is recorded as complete-response time and used only as an
upper bound for per-conclusion availability. It is not token-level latency.

For a locally available prompt-only consumer, `collect_consumer.py` performs
the explicit subprocess call, persists only the structured response and
per-metric report, and refuses to replace an existing output directory:

```bash
python eval/bundle-consumption/collect_consumer.py \
  --catalog eval/investigation-quality/fixtures/scenarios.json \
  --bundle-root .aet/eval/bundle-consumption/generated \
  --consumer-id local-consumer \
  --runtime-version <runtime-version> \
  --model-id <model-id> \
  --output-dir .aet/eval/bundle-consumption/local-consumer \
  -- <consumer-command>
```

The command is never inferred or run by the AET evidence runtime. This helper
exists only for an explicitly requested evaluation run.

For Hermes, use the one-shot interface with an explicit configured model so
the process writes only the final response to standard output:

```bash
python eval/bundle-consumption/collect_consumer.py \
  --catalog eval/investigation-quality/fixtures/scenarios.json \
  --bundle-root .aet/eval/bundle-consumption/generated \
  --consumer-id hermes-prompt-only \
  --runtime-version <hermes-version> \
  --model-id <configured-model> \
  --output-dir .aet/eval/bundle-consumption/hermes \
  --prompt-mode argument \
  -- hermes -m <configured-model> -t '' --ignore-rules -z
```

Ollama's generic `--format json` mode does not by itself guarantee that a
model will satisfy the Review collection shape. The local baseline therefore
uses a complete JSON Schema through the loopback API, parses the model's
response, and serializes it again before the collector accepts it:

```bash
python eval/bundle-consumption/collect_consumer.py \
  --catalog eval/investigation-quality/fixtures/scenarios.json \
  --bundle-root .aet/eval/bundle-consumption/generated \
  --consumer-id qwen3-local-structured-prompt-only \
  --runtime-version <ollama-version> \
  --model-id qwen3:8b \
  --output-dir .aet/eval/bundle-consumption/qwen3 \
  -- python eval/bundle-consumption/ollama_structured_consumer.py
```

The collector then performs a second strict parse that rejects duplicate keys,
non-finite values, a missing scenario, or any extra scenario. Parse success is
still separate from semantic success: the per-scenario scorer checks Bundle
identity, citation kinds, counter-evidence, Freshness, and unknown boundaries.

`publish_collection.py` accepts only a collection whose report can be rebuilt
exactly from its structured response and elapsed metadata. Runtime identity,
model identity, and the command-argv hash must already be fixed by
`collect_consumer.py`; publication cannot replace them. It publishes those
sanitized JSON artifacts with per-file SHA-256 values, while private runtime
transcripts are never copied.

The measured v1.14.0 synthetic-fixture summary is published at
`results/v1.14.0.json`. It reports each metric independently and records an
unavailable local consumer as `NOT_APPLICABLE`; it is not a general model
accuracy claim.

Generate the ten repeatable synthetic Bundle fixtures:

```bash
python eval/bundle-consumption/generate_fixtures.py \
  --output eval/bundle-consumption/generated
```

Generation is local and deterministic. It makes no external Agent calls,
contains no measured consumer result, and refuses to overwrite an existing
output directory. The scenario catalog keeps `availability: not_collected`
until an independently produced Review Result is explicitly attached.
