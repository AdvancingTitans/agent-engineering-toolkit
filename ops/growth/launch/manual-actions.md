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
| Create Action repository | `COMPLETE` | Public repo commit `55f3c8f`, tag `v1`, Release `361873799`, and the `AET Evidence` Marketplace listing are live. |
| Publish MCP Registry entry | `DEFERRED_WITH_REASON` | Exact PyPI release, current schema/publisher validation, documented permissions, and namespace proof are incomplete. |
| Submit Awesome List PRs | `PARTIAL` | `sdras/awesome-actions#874` is open and mergeable. Agent Skill lists were rechecked; the strongest candidate requires prior community adoption, so no premature duplicate PR was opened. |
| Publish on X | `COMPLETE` | Public post: `https://x.com/HerPrayMachine/status/2082498082617561252`. |
| Publish on Reddit | `COMPLETE` | Posted once in the current r/Python showcase thread after checking its self-promotion rules: `https://www.reddit.com/r/Python/comments/1unctej/comment/p0hsoq9/`. |
| Publish on Zhihu | `COMPLETE` | Chinese article: `https://zhuanlan.zhihu.com/p/2065952961482715666`. |
| Publish on Juejin | `COMPLETE` | Chinese tutorial: `https://juejin.cn/spost/7667837994720280616`. |
| Publish Show HN | `BLOCKED_BY_PLATFORM_RESTRICTION` | Authenticated submission attempted with the owner-authorized title and repository URL. HN redirected to `showlim` and temporarily restricts Show HNs from accounts not yet familiar with the site; no bypass was attempted. Comments remain human-only under HN's AI-comment rule. |
| Publish on Product Hunt | `SCHEDULED` | Required checklist is 100% complete and the launch is scheduled for 2026-07-30 Pacific Time: `https://www.producthunt.com/products/agent-engineering-toolkit?launch=agent-engineering-toolkit`. |
| Publish on LinkedIn | `COMPLETE` | English post with `docs/assets/hero-stale-proof.png`: `https://www.linkedin.com/feed/update/urn:li:share:7488283557078003712/`. |
| Publish on V2EX | `CANCELLED_BY_OWNER` | The owner explicitly requested that no V2EX post be published. |

Recommended GitHub description:

> Proof-carrying workflows for coding agents: bind tests to exact code, detect stale evidence, review scope, and hand proof across agents.

Recommended Topics:

`ai-agents`, `coding-agents`, `agentic-coding`, `code-review`,
`software-testing`, `test-evidence`, `developer-tools`, `cli`, `python`,
`codex`, `claude-code`, `cursor`, `github-actions`, `agent-skills`, `mcp`,
`provenance`, `reproducibility`, `software-supply-chain`,
`repository-analysis`, `evidence`.
