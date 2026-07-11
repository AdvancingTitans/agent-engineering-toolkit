# `aet evolve` contract

`evolve` is the Repo Archaeologist surface of AET. It answers what changed,
when, and which sources link the facts. It does not assert an author's intent.

```bash
aet evolve plan . --question "Why did this API change?" --output .aet/evolve/plan.json
aet evolve collect . --question "Why did this API change?" --output .aet/evolve/run
aet evolve build --manifest .aet/evolve/run/source-manifest.json --output .aet/evolve/run
aet evolve report --graph .aet/evolve/run/object-graph.json --output .aet/evolve/run
aet evolve query --graph .aet/evolve/run/object-graph.json --question "release"
```

Local Git sources are L3, local documents L1. A supplied GitHub JSON export is
recorded as local evidence; explicit `--remote github` records API retrieval as
L4 and reports unavailable access as `UNKNOWN`. Links are `DIRECT` only for a
reproducible object relation (for example tag → commit); textual `#123`
mentions remain `CANDIDATE` until the target object is present.
