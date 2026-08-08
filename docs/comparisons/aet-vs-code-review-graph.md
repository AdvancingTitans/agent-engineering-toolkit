# AET Review Graph and code-review-graph

This page explains the overlap and the boundary between two different tools.
It is not a head-to-head benchmark.

[`code-review-graph`](https://github.com/tirth8205/code-review-graph) builds a
persistent structural code graph with Tree-sitter and SQLite. Its documented
strength is broad multi-language, incremental code indexing for blast-radius
analysis and low-context structural exploration through MCP.

AET Review Graph builds a hash-bound review package from the current Git
snapshot, a Python AST index, a Portable Evidence Bundle, Improvement records,
and explicit human constraints. Its strength is carrying code relations
together with evidence authority, permitted scope, protected paths,
verification requirements, limitations, freshness, and stop conditions.

| Dimension | AET Review Graph v1.19 | code-review-graph at reviewed commit |
| --- | --- | --- |
| Primary question | What may this review conclude or change, on which evidence, and when must it stop? | Which code is structurally connected to this change? |
| Code indexing | Python AST, package-local snapshot | Tree-sitter, broad language support, persistent SQLite index |
| Incremental index | No; rebuilds the bounded package | Yes |
| Evidence and authority | First-class Claim, Evidence, scope, test, limitation, and stop nodes | Code structure is the primary graph |
| Default Agent input | Hash-bound `review/root.slice.json` | Bounded graph-query results through MCP/CLI |
| Staleness | Git/package drift returns `UNKNOWN` and stops | Index refresh and graph freshness follow that project's own lifecycle |
| Human projection | Mermaid and Markdown derived from the same package | Graph inspection and repository guidance |

## Context measurements are not comparable

The AET README reports a 23.2% byte reduction for one frozen AET Python case:
6,505 bytes for the root slice versus 8,468 bytes for the minimum raw materials
needed for the same diagnosis. The `code-review-graph` repository reports its
own whole-corpus and changed-file experiments under a different corpus,
baseline, query contract, and measurement method. Neither number supports a
cross-project speed, token, accuracy, or quality ranking.

Use `code-review-graph` when broad, persistent structural navigation is the
main need. Use AET Review Graph when the review must carry evidence and human
authority boundaries with the code relationships. They can also be composed:
a future AET code-index adapter could consume a broader structural index while
preserving AET's package and authority contract.

## Reviewed source

This comparison was checked against `code-review-graph` commit
`1a010deed6c283d4aa1e7e949e78fe3a7bcdfbb3`. Product behavior can change after
that commit; consult its current README and benchmark documentation before
making adoption decisions.
