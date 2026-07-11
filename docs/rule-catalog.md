# AET rule catalog

| Rule | Meaning | Default gate effect |
| --- | --- | --- |
| `AET-CTX-001` | Relative Markdown or inline local target is missing. | FAIL |
| `AET-CTX-002` | Explicit local Python/shell command target is missing. | FAIL |
| `AET-CTX-003` | An absolute local instruction path is stale. | FAIL |
| `AET-CTX-004` | Root instruction file risks always-on context bloat. | UNKNOWN/WARN |
| `AET-CTX-005` | A long directive is duplicated across context assets. | UNKNOWN/WARN |
| `AET-SKL-001` | Skill has no required `name` / `description` frontmatter. | FAIL |
| `AET-SKL-002` | Skill directory and frontmatter name disagree. | FAIL |
| `AET-SKL-004` | Skill does not state a completion check. | UNKNOWN/WARN |
| `AET-REV-001..004` | Intent contract validity, scope budget, allowed paths, and declared evidence. | FAIL where violated |

`UNKNOWN` is a verification gap, not a discounted PASS. Use `aet triage` only
to order remediation; it is deliberately not a gate.
