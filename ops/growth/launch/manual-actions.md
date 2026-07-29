# Manual actions and external state

No item in this file authorizes Codex or a workflow to perform the action.

| Action | Current state | Human requirement |
| --- | --- | --- |
| Publish v1.18 GitHub Release | `COMPLETE` | Release Run `30466008349`; six exact CI assets published. |
| Publish v1.18 to PyPI | `COMPLETE` | Trusted Publishing Run `30466191944`; public wheel and clean `uvx` verified. |
| Update GitHub About description | `COMPLETE` | Frozen description published. |
| Set Homepage | `COMPLETE` | `https://advancingtitans.github.io/agent-engineering-toolkit/`. |
| Update Topics | `COMPLETE` | All 20 approved topics published. |
| Upload Social Preview | `COMPLETE` | Uploaded `site/assets/social-preview.png`. |
| Enable GitHub Pages | `COMPLETE` | Pages workflow attempt 2 passed and the public site is live. |
| Enable Discussions | `COMPLETE` | Enabled; Known limitations published as Discussion #5. |
| Pin repository on profile | `COMPLETE` | Repository was already pinned; no change required. |
| Verify Community Profile | `COMPLETE` | GitHub reports 100% health after community files landed. |
| Verify five skills.sh pages | `UNAVAILABLE` | All five routes return HTTP 200 fallback pages stating the Skill is not available in this repository. |
| Create Action repository | `BLOCKED_LEGAL_CONFIRMATION` | Public repo, tested template, commit `55f3c8f`, and tag `v1` exist; Marketplace publication requires action-time confirmation before accepting its legal terms. |
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
