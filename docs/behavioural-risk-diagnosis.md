# Evidence-grounded behavioural risk diagnosis

`aet risk diagnose` is an AET Lab surface for deterministic, local, read-only diagnosis of one normalized Agent run. It consumes existing canonical Run Records, an explicit Intent v2 contract, a reviewed risk policy, and optional evidence. It does not train or modify a model, call a model API, infer a stable internal motive, create a single aggregate risk rating, or execute an intervention.

## Risk vector

- `goal_divergence_indicator` records behaviour relative to explicit user/project intent. It does not prove a stable motive, malice, or consciousness.
- `harm_realization_capability` records a protected action proven successful under the current deployment permissions. It does not establish general model capability.
- `oversight_resistance_indicator` requires an observed action and effect against a declared monitoring surface. A missing log or failed monitor is an `observability_gap`, not evidence of evasion.

Each axis preserves `PASS`, `FAIL`, `UNKNOWN`, or `NOT_APPLICABLE`, evidence and counter-evidence references, coverage, limitations, and `does_not_prove`. `PASS` requires complete declared coverage. Missing, truncated, orphaned, stale, redacted, or actor-ambiguous evidence remains `UNKNOWN`.

## Pathways and authority

A pathway may connect two or three failed factors only when they share the same run group, generation, task and relevant asset/monitoring scope, have ordered evidence, and have no unresolved coverage gap. The sequence remains observational and is not an internal-causality claim.

Interventions use a fixed decision table and always carry `authority: PROPOSED`. AET has no interface that terminates a run, revokes credentials, isolates a machine, changes a monitor, or contacts a person. The Agent Host and responsible human must independently inspect the cited evidence and decide.

## Offline validation

The diagnosis release gate replays nine hash-bound action/outcome summaries from three matched clean/blocked/unsafe AgentDojo triads. Labels come from AgentDojo's programmatic scorers at one pinned upstream commit; AET does not call a model or the network during replay. Only decision-bearing tool names, status, and hashes are retained. This supports a bounded diagnosis-conformance claim, not raw AgentDojo ingestion, human usability, monitoring-evasion accuracy, or general model safety.

The original synthetic suite remains a contract regression for edge cases and Codex/Claude Code parity. It is not represented as an independently human-labelled gold set.

## Prediction boundary

The diagnosis is not a validated prediction. Forecast promotion is hard-disabled as `research_only` in this release, so every pathway forecast remains `UNKNOWN` even when an input file declares plausible calibration metrics. A future version may reconsider promotion only after those metrics are derived from frozen raw outcomes with independent time/repository/host holdouts. The public diagnosis corpus is not forecast calibration.
