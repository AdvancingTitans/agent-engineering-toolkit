# AET Quick investigation comparison

This directory is an opt-in AET Lab benchmark. It does not add a Quick CLI
command and is not a release gate.

## Fixed comparison

The suite has four fixed groups:

1. `pure_rules`: deterministic fixture-declared rule findings, with zero model
   or tool usage;
2. `one_shot_llm`: one model judgment over the supplied task and facts, without
   an investigation loop;
3. `investigated_aet`: bounded hypothesis and counter-hypothesis investigation;
4. `investigated_grounded`: a distinct grounding-aware Agent configuration
   that requires counter-explanation fields, followed by the shipped
   `validate_investigated_finding` Grounding Validator; rejected claims do not
   survive into scoring.

The fourth group is not a paired ablation of the third group. Its Prompt,
structured output requirements, and post-processing Validator all differ.
The Validator consumes a fixture-synthesized Ledger because every scenario
fact is supplied up front; this measures constrained Claim validation, not
end-to-end evidence acquisition from a real repository.

The eight scenarios are the scope cases frozen by the Quick design:

- explicit scope violation;
- justified shared-module change;
- ambiguous intent;
- later user authorization;
- unrelated dependency;
- required multi-module interface migration;
- unsupported counter-hypothesis;
- exhausted investigation budget.

All groups use the same four claim IDs. The catalog is visible to the model,
but the expected claim set is used only by the scorer. This avoids scoring
arbitrary prose or relying on an LLM judge.

## Run

Run the deterministic baseline:

```bash
python eval/quick-investigation/runner.py \
  --group pure_rules \
  --output .aet/quick-benchmark/runs
```

Run all groups three times with the same model and parameters:

```bash
python eval/quick-investigation/runner.py \
  --group all \
  --model gpt-5 \
  --model-param 'model_reasoning_effort="medium"' \
  --repetitions 3 \
  --output .aet/quick-benchmark/runs
```

Reproduce the exact v1.13.0 sampling configuration in a fresh output directory:

```bash
python eval/quick-investigation/runner.py \
  --suite eval/quick-investigation/fixtures/scope-scenarios.json \
  --group all \
  --model gpt-5.6-sol \
  --model-param 'model_reasoning_effort="medium"' \
  --repetitions 2 \
  --output .aet/quick-benchmark-v1.13.0-reproduction/runs

python eval/quick-investigation/scorer.py \
  --suite eval/quick-investigation/fixtures/scope-scenarios.json \
  --runs .aet/quick-benchmark-v1.13.0-reproduction/runs \
  --output .aet/quick-benchmark-v1.13.0-reproduction/report.json
```

Model sampling is nondeterministic, so a rerun is a repeated observation rather
than a promise of byte-identical values. The tracked
`results/v1.13.0-normalized-runs.json` contains the privacy-reviewed normalized
Runs used for the published table and can be rescored directly with `--runs`.

The harness calls `codex exec --json` in an isolated per-run read-only
workspace. Each model run stores the private raw JSONL, stderr, final response,
and normalized `run.json`. Do not publish raw JSONL without reviewing it for
private prompt or repository content.

The runner refuses to overwrite an existing run directory. Use a new output
directory for a new sample. The selected model and canonical JSON model
parameters are recorded on every model run, allowing repeated observations
under one configuration.

## Codex JSONL measurements

The standard-library parser uses completed Codex events:

- `turn.completed.usage.input_tokens`;
- `turn.completed.usage.output_tokens`;
- `turn.completed.usage.reasoning_output_tokens`;
- completed `command_execution`, `mcp_tool_call`, and `tool_call` items;
- external monotonic wall time around the Codex process.

Tool items are deduplicated by their Codex item ID. A missing
`turn.completed.usage` is recorded as `UNKNOWN`, not zero consumption.
Malformed or missing final JSON produces output status `UNKNOWN`, not a guessed
result.

## Score

```bash
python eval/quick-investigation/scorer.py \
  --runs .aet/quick-benchmark/runs \
  --output .aet/quick-benchmark/report.json
```

The deterministic scorer reports, per group:

- effective recall: expected claim IDs emitted / expected claim IDs;
- false discovery proportion: emitted Claim IDs outside the expected set,
  divided by all emitted Claim IDs;
- ungrounded conclusions: claims with no evidence reference or a reference
  outside the scenario;
- Grounding rejections recorded per Run before scoring;
- tool-call total and mean;
- wall-time total and mean;
- input, output, reasoning, and total Token totals and means.

These metrics describe only the declared eight-case suite and sampled model
runs. They are not a holistic trust score and cannot authorize release or
adoption.

## Human annotations

Manual review time and user understanding cannot be derived from JSONL. Copy
`annotations.example.json`, replace the example with actual observations, and
score with:

```bash
python eval/quick-investigation/scorer.py \
  --runs .aet/quick-benchmark/runs \
  --annotations path/to/actual-annotations.json \
  --output .aet/quick-benchmark/report.json
```

`manual_review_seconds` must be an actual timed non-negative duration.
`user_understanding` must be explicitly annotated as `CORRECT`, `PARTIAL`, or
`INCORRECT`. When no annotation exists, both per-run and aggregate fields stay
`UNKNOWN`; the scorer never fills or infers them.

## Contracts

- `schemas/suite-v1.schema.json`: fixed groups and eight scenarios;
- `schemas/run-v1.schema.json`: normalized provenance and measured usage;
- `schemas/normalized-runs-v1.schema.json`: privacy-reviewed, rescorable Run bundle;
- `schemas/annotations-v1.schema.json`: optional human-only observations;
- `fixtures/scope-scenarios.json`: the tracked comparison suite.
