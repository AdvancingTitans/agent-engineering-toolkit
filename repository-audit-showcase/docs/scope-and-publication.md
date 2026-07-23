# Repository Audit Showcase v1 Boundary

The three cases are static, read-only audits of commit-locked local checkouts.
They do not install dependencies, execute upstream code, run upstream tests, or
send source code to an LLM.

Reports contain repository-relative paths, line numbers, classifications, and
content hashes. They do not redistribute upstream source text. Findings are
engineering observations, not defect, vulnerability, affiliation, or upstream
endorsement claims.

`evidence_manifest.json` and `findings.json` are shared machine artifacts.
Human-readable summaries, Markdown, HTML, Agent-flow SVG, and evidence-chain
SVG are rendered under both `en/` and `zh-CN/`. Both locales preserve the same
Finding IDs, statuses, severity, impact, evidence locations, and review state.

Publication requires a maintainer review. Generated reports remain `PENDING`
until that review is completed. The tracked v1.12.0 snapshots for all three
locked commits were reviewed and approved for publication; their review state
is `APPROVED`.

OpenHands content below `enterprise/` and `tests/**/enterprise/` is prohibited
from evidence collection because it is outside the root MIT boundary.
