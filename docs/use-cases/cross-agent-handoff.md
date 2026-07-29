# Cross-Agent evidence handoff

A reviewer should not need the same Agent host—or even an AET installation—to
inspect the evidence.

A Portable Evidence Bundle contains authoritative JSON/JSONL records,
content-addressed references, explicit limitations, and a deterministic
Markdown projection:

```text
evidence-bundle/
├── manifest.json
├── index.json
├── core/{claims,evidence,observations}.jsonl
├── archive/{sources,diagnostics,conflicts,ledger}.jsonl
├── policy.json
├── consumer-guide.md
└── report.md
```

The reviewer can read these files directly. Convenience SDK and MCP surfaces
do not change authority. Observations remain separate from verified Evidence;
counter-evidence remains visible; missing proof stays `UNKNOWN`.

See the [complete technical overview](../reference/full-product-overview.md)
for creation, validation, Atlas, Improvement, and Planner commands.
