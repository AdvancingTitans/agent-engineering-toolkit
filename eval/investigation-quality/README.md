# Investigation quality scenario catalog

`fixtures/scenarios.json` freezes the ten Portable Bundle consumption
categories required by the implementation plan. The catalog is an evaluation
worklist, not measured model evidence.

Entries with `availability: not_collected` intentionally produce
`NOT_APPLICABLE` metrics. A future measured run may switch one entry to
`available` and add Bundle and Review paths relative to the catalog. That
change must preserve the scenario category and retain the raw per-metric
report; it must not introduce an aggregate trust score.
