# Evidence Atlas architecture

Evidence Atlas is the deterministic, recursive visualization layer for a
Portable Evidence Bundle. It makes evidence relationships easier to inspect;
it does not create evidence or change its authority.

## Authority contract

```text
Bundle records
  → canonical Evidence Graph
    → deterministic Perspectives
      → bounded recursive hierarchy
        → Mermaid / Markdown / JSON / offline Viewer
```

The reverse direction is forbidden. Mermaid and Viewer content cannot promote
an Observation, change a Claim status, refresh a stale Proof, remove
counter-evidence, resolve `UNKNOWN`, or authorize a repository action.

Bundle v1 validators require `manifest.json` and `index.json` to identify the
exact files in a Bundle. Atlas therefore defaults to the sibling sidecar
`<bundle>.atlas/`; the sidecar binds itself to the Bundle content hash and
manifest/index SHA-256 values.

## Canonical graph

`aet atlas build` creates:

```text
<bundle>.atlas/
├── graph/
│   ├── graph.json
│   ├── nodes.jsonl
│   ├── edges.jsonl
│   ├── hierarchy.json
│   ├── diagnostics.jsonl
│   ├── candidates/edges.jsonl
│   └── perspectives/
└── atlas/
    ├── index.html
    └── assets/
```

Every authoritative node and edge has at least one field-level `source_ref`.
The graph uses discrete evidence states instead of a holistic trust score.
Stale proof records retain their historical result but cannot produce a current
`VALIDATES` edge.

Candidate edges suggested by a future host LLM belong only in
`graph/candidates/edges.jsonl`. They are non-authoritative until deterministic
code can ground them in Bundle references. The complete build works with
`--no-llm`; the v1.15 core rejects attempts to make an LLM authoritative.

## Perspectives and recursive decomposition

The fixed v1 Perspectives are:

1. `claim-chain`
2. `investigation-flow`
3. `change-scope`
4. `verification-coverage`
5. `evidence-data-flow`
6. `integrations`
7. `conflicts`
8. `freshness`

Each Perspective contains `perspective.json`, `diagram.mmd`,
`diagram-ir.json`, provenance, and the documented question, description,
context, evidence, counter-evidence, Freshness, constraints, concerns,
unknowns, and actions. Recursive node directories use the same projection
contract.

Every node receives a deterministic complexity score and one of
`leaf`, `expandable`, or `mandatory_decomposition`. Type-specific decomposers
expand Findings, Claims, change groups, Proofs, and integrations. Hard budgets
bound depth, nodes per diagram, children per node, and total diagrams.
Canonical node IDs deduplicate repeated evidence. Cycles terminate as reference
nodes.

## Rendering and security

Perspective queries produce a Diagram IR before Mermaid. The renderer supports
`flowchart`, `sequenceDiagram`, `timeline`, and `stateDiagram`. It generates
stable safe IDs, escapes and truncates labels, and forbids HTML labels, remote
images, external URLs, click directives, and scripts.

The static Viewer vendors a pinned Mermaid runtime and initializes it with
`securityLevel: "strict"`. It performs no network request and requires no AET,
Python, Node, SDK, MCP server, or account. If Mermaid rendering fails, the
graph, Markdown, provenance, diagnostics, and list-based Viewer fallback remain
available.

The three Viewer columns provide Perspective/tree navigation, the current
diagram, and evidence details. It supports search, status filters, supporting,
counter-evidence, and stale-path highlighting, recursive child navigation,
parent history, raw JSON, and source references.

## Incremental rebuilds and comparison

Atlas records indexes from Bundle records to nodes, edges, Perspectives, and
parent diagrams. On rebuild, input record hashes identify the affected
projections. Validated unchanged Perspective directories are reused directly;
changed Perspectives and parent complexity are rebuilt. If a changed record
cannot be mapped safely, the builder rebuilds all Perspectives.

`aet atlas diff` compares graph identity, nodes, edges, Claim states,
Freshness, conflicts, and resolved or newly introduced unknowns. It never emits
a combined trust score.

## Validation

`aet atlas validate` checks at least:

- Bundle identity and input hashes;
- JSON Schema conformance;
- node and edge source references;
- authority and evidence-strength boundaries;
- counter-evidence and `UNKNOWN` retention;
- stale Proof propagation;
- recursive depth, node, child, and diagram budgets;
- cycle/reference behavior and child links;
- Mermaid syntax and prohibited constructs;
- offline Viewer assets and local Mermaid runtime.

A Mermaid failure does not invalidate or rewrite the source Bundle. Atlas
diagnostics remain explicit and the authoritative JSON/JSONL stays usable.

## Consumer APIs

The CLI supports `build`, `validate`, `view`, `export`, `query`, `explain`, and
`diff`. Python and TypeScript SDKs expose graph load/build/query/subgraph/trace,
validation, and Mermaid rendering. MCP exposes eight read-only
`aet_graph_*` tools and returns bounded slices rather than an unbounded graph.

The reproducible repository self-review is in
[`examples/evidence-atlas`](../../examples/evidence-atlas).
