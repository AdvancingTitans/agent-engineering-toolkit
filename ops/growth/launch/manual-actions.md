# Manual actions and external state

No item in this file authorizes Codex or a workflow to perform the action.

| Action | Current state | Human requirement |
| --- | --- | --- |
| Publish v1.18 GitHub Release | `BLOCKED` | Complete all local and cross-OS gates; publish exact CI artifact. |
| Publish v1.18 to PyPI | `BLOCKED` | PyPI is v1.11.1; owner `Young_Tommy` must verify Trusted Publishing and promote the exact artifact. |
| Update GitHub About description | `MANUAL_NOT_STARTED` | Use the frozen description in `ops/growth/positioning.md`. |
| Set Homepage | `MANUAL_NOT_STARTED` | Enable Pages first, then use the final Pages URL. |
| Update Topics | `MANUAL_NOT_STARTED` | Review and set no more than 20 approved topics. |
| Upload Social Preview | `MANUAL_NOT_STARTED` | Upload `site/assets/social-preview.png`. |
| Enable GitHub Pages | `BLOCKED` | Pages API returned 404 and repository reports `has_pages=false`; enable from `site/`. |
| Enable Discussions | `BLOCKED` | Repository reports `has_discussions=false`; enable before relying on Discussion forms. |
| Pin repository on profile | `MANUAL_NOT_STARTED` | Maintainer decision. |
| Verify Community Profile | `MANUAL_NOT_STARTED` | Baseline health was 57%; recheck after community files land. |
| Verify five skills.sh pages | `UNAVAILABLE` | Search did not return the AET Skills on 2026-07-29; run isolated install and wait for indexing. |
| Create Action repository | `MANUAL_NOT_STARTED` | Create `AdvancingTitans/aet-evidence-action`, copy only the template, test, accept Marketplace terms, and publish manually. |
| Publish MCP Registry entry | `DEFERRED_WITH_REASON` | Exact PyPI release, current schema/publisher validation, documented permissions, and namespace proof are incomplete. |
| Submit Awesome List PRs | `MANUAL_NOT_STARTED` | Read each list's current rules and submit only individually relevant entries. |
| Publish external channel content | `MANUAL_NOT_STARTED` | Human owner must rewrite, verify current rules, and post manually. |

Recommended GitHub description:

> Proof-carrying workflows for coding agents: bind tests to exact code, detect stale evidence, review scope, and hand proof across agents.

Recommended Topics:

`ai-agents`, `coding-agents`, `agentic-coding`, `code-review`,
`software-testing`, `test-evidence`, `developer-tools`, `cli`, `python`,
`codex`, `claude-code`, `cursor`, `github-actions`, `agent-skills`, `mcp`,
`provenance`, `reproducibility`, `software-supply-chain`,
`repository-analysis`, `evidence`.
