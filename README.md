# Agent Engineering Toolkit

[简体中文](docs/README.zh-CN.md) · [Start here](docs/start-here.md) · [Full product reference](docs/reference/full-product-overview.md)

> **Your coding agent says tests passed. AET proves which code was actually tested.**

**Proof-carrying workflows for coding agents.** AET binds test runs, changed
files, artifacts, and agent claims into portable evidence, then tells you when
that proof no longer applies.

```bash
uvx --from agent-engineering-toolkit aet demo stale-proof
```

> Released in [AET v1.18.0](https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/tag/v1.18.0)
> and verified from the public PyPI package.

```text
AET stale-proof demo

1. Test command executed                    PASS
2. Proof matches the tested source          EXACT_MATCH
3. Source changed without rerunning tests   RELEVANT_FILES_CHANGED

The test really passed, but that proof no longer applies to the current code.
Demo result: PASS
```

![AET detects stale test proof](docs/assets/hero-stale-proof.png)

AET is not another coding agent. AET does not replace tests or CI. It does not
turn missing evidence into `PASS`, and it does not auto-edit, auto-commit,
push, merge, or release.

## What the demo proves

The installed demo runs a real standard-library test in a temporary Git
repository, records a Quick Proof against the exact fixture source, verifies
`EXACT_MATCH`, changes a declared relevant file without rerunning the test, and
then reports `RELEVANT_FILES_CHANGED`.

That means:

- the test really executed and passed;
- the historical result remains a real fact;
- the old proof no longer applies to the changed source;
- the expected stale detection makes the demo itself pass.

It does **not** prove that every test passed, that an Agent's implementation is
correct, or that a change should be merged. Git is required. Missing
dependencies, unreadable fixtures, timeouts, and broken proof data fail closed
as `UNAVAILABLE`, `UNKNOWN`, or a nonzero exit.

## Four Quick Skills

| Question | Skill | CLI |
| --- | --- | --- |
| Are Agent instructions usable and verifiable? | `/aet-check` | `aet quick check .` |
| Does this diff stay inside the approved task? | `/aet-scope` | `aet quick scope . --base main --intent aet.intent.json` |
| Did this exact command run on these files? | `/aet-proof` | `aet quick proof --output proof.json --relevant-path src/app.py -- python -m unittest` |
| Does an older proof still apply? | `/aet-fresh` | `aet quick fresh --proof proof.json` |
| What should change, without editing yet? | `/aet-plan` | `aet plan context ...` |

The first four are bounded daily Quick surfaces. `/aet-plan` is a separate,
read-only `PROPOSED` planning handoff; it never grants implementation or
verification authority.

## Real workflows

### Stale proof

A green log can be historically true and currently inapplicable. See the
[reproducible stale-proof case](docs/use-cases/stale-proof.md).

### Scope drift

AET distinguishes task-relevant cross-module work from unrelated expansion;
it does not treat every multi-file change as scope drift. See
[scope drift](docs/use-cases/scope-drift.md).

### Cross-Agent handoff

A reviewer without AET installed can consume the JSON/JSONL records and
Markdown projection in a Portable Evidence Bundle. See
[cross-Agent handoff](docs/use-cases/cross-agent-handoff.md).

## Install

| Path | Command | Status |
| --- | --- | --- |
| Public package | `uv tool install agent-engineering-toolkit` | PyPI v1.18.0 |
| One-shot demo | `uvx --from agent-engineering-toolkit aet demo stale-proof` | Publicly verified |
| Exact Release wheel | `uv tool install https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/download/v1.18.0/agent_engineering_toolkit-1.18.0-py3-none-any.whl` | GitHub Release asset |
| Agent Skills | `npx skills add AdvancingTitans/agent-engineering-toolkit` | External CLI; see telemetry note |

To opt out of the skills.sh CLI's anonymous installation telemetry:

```bash
DISABLE_TELEMETRY=1 npx skills add AdvancingTitans/agent-engineering-toolkit
```

AET itself adds no telemetry, account, API key, model call, or cloud service.
Python 3.11+ is required.

## Use it with your Agent

- [Codex](docs/integrations/codex.md)
- [Claude Code](docs/integrations/claude-code.md)
- [Cursor](docs/integrations/cursor.md)
- [GitHub Actions](docs/integrations/github-actions.md)
- [skills.sh](docs/integrations/skills-sh.md)
- [MCP](docs/integrations/mcp.md)

Start with the [five-minute guide](docs/start-here.md), then use the smallest
surface that answers your question. For precise state and authority semantics,
read [status and authority](docs/reference/status-and-authority.md).

## How AET relates to existing tools

- [AET vs Plan Mode](docs/comparisons/aet-vs-plan-mode.md)
- [AET vs CI](docs/comparisons/aet-vs-ci.md)
- [AET vs observability](docs/comparisons/aet-vs-observability.md)

CI verifies checks. AET records what ran, what it was bound to, and whether that
evidence still applies. Plan Mode proposes work. AET can ground a bounded plan
without executing it. Observability explains broad system behavior. AET
focuses on local engineering evidence and authority.

## Advanced product surfaces

Portable Evidence Bundles, Evidence Atlas, grounded Improvements,
Evidence-Guided Planner, evaluation suites, schemas, release gates, and
Repository Evolution remain supported. They are intentionally not all first-
screen concepts. See the [complete technical overview](docs/reference/full-product-overview.md).

Freshness remains explicit: `EXACT_MATCH`, `RELEVANT_FILES_MATCH`,
`HEAD_CHANGED_RELEVANT_FILES_MATCH`, `RELEVANT_FILES_CHANGED`,
`ARTIFACT_CHANGED`, `ENVIRONMENT_CHANGED`, or `UNKNOWN`.

## Evidence-Guided Planner

The v1.17 Planner is a separate read-only `PROPOSED` surface built on v1.16
evidence. It performs bounded localization, preserves `NEEDS_EVIDENCE` and
`UNKNOWN`, and never implements edits. In one bounded real case—not a general
model-quality claim—production decision precision moved from 44.44% to 100%
(+55.56 points). See the [full product reference](docs/reference/full-product-overview.md).

## Real-world Repository Audit Showcase

The commit-locked static cases remain in the [full product reference](docs/reference/full-product-overview.md).

<!-- atlas-self-review-mermaid:start -->
```mermaid
flowchart LR
    %% Evidence Atlas
    N_0b51dce8fe915eda{"[CONFLICT] The Bundle v1 change-scope view alone proves complete real diff grouping."}
    N_6f91af1641ed1424{{"[SUPPORTED] AET projects ten fixed evidence perspectives and exposes complex nodes as recursive Viewer subg..."}}
    N_8575658723b5d49d{{"[SUPPORTED] AET builds a canonical Evidence Graph from source-backed Bundle records without letting Mermaid..."}}
    N_5522d8dace1cb6e7{"[CONFLICT] Path binding is useful for scope context but insufficient to prove complete real diff grouping."}
    N_ac65699e766edc85["[UNKNOWN] Unresolved conflict conflict-change-scope-v1"]
    N_ef4722a060cacfda["[VERIFIED] Bundle Evidence records can bind facts to repository paths."]
    N_1ded0fae46344828["[VERIFIED] The Portable Evidence v1 Evidence record schema does not define an explicit Change Group field."]
    N_c075a66077dd6940["[VERIFIED] The Graph Builder creates canonical nodes and source-backed edges."]
    N_e824b2ad012b224e["[VERIFIED] The Perspective module defines ten fixed deterministic projections."]
    N_a42d56cfe9dff13d["[VERIFIED] The offline Viewer contains recursive subgraph navigation."]
    N_f797fb20a8448aa0["[RECORDED] Review AET's own Evidence Atlas implementation and retain support, counter-evidence, limitation..."]
    N_a17fb3165e6b0db5["[RECORDED] The view must display UNKNOWN rather than infer real diff groups."]
    N_6630b028247f1a08["[RECORDED] Rendering success still requires the packaged Mermaid runtime."]
    N_2eb930959384d64c["[OMITTED] 17 lower-priority nodes"]
    N_0b51dce8fe915eda -.->|"contradicted by"| N_1ded0fae46344828
    N_0b51dce8fe915eda -->|"limited by"| N_a17fb3165e6b0db5
    N_0b51dce8fe915eda ==>|"supported by"| N_ef4722a060cacfda
    N_5522d8dace1cb6e7 -.->|"contradicted by"| N_1ded0fae46344828
    N_5522d8dace1cb6e7 -->|"leaves unknown"| N_ac65699e766edc85
    N_5522d8dace1cb6e7 -.->|"contradicted by"| N_ef4722a060cacfda
    N_6f91af1641ed1424 -->|"limited by"| N_6630b028247f1a08
    N_6f91af1641ed1424 ==>|"supported by"| N_a42d56cfe9dff13d
    N_6f91af1641ed1424 ==>|"supported by"| N_e824b2ad012b224e
    N_8575658723b5d49d ==>|"supported by"| N_c075a66077dd6940
    N_0b51dce8fe915eda -->|"answers"| N_f797fb20a8448aa0
    N_6f91af1641ed1424 -->|"answers"| N_f797fb20a8448aa0
    N_8575658723b5d49d -->|"answers"| N_f797fb20a8448aa0
    classDef verified fill:#dcfce7,stroke:#166534,color:#052e16,stroke-width:2px
    classDef observation fill:#e0f2fe,stroke:#0369a1,color:#082f49
    classDef candidate fill:#fef3c7,stroke:#92400e,color:#451a03,stroke-dasharray:5 3
    classDef supported fill:#ede9fe,stroke:#6d28d9,color:#2e1065,stroke-width:2px
    classDef unsupported fill:#fee2e2,stroke:#b91c1c,color:#450a0a,stroke-width:2px,stroke-dasharray:5 3
    classDef conflict fill:#fee2e2,stroke:#b91c1c,color:#450a0a,stroke-width:2px
    classDef unknown fill:#f3f4f6,stroke:#4b5563,color:#111827,stroke-dasharray:5 3
    classDef stale fill:#ffedd5,stroke:#c2410c,color:#431407,stroke-dasharray:3 3
    classDef authorization fill:#ecfccb,stroke:#3f6212,color:#1a2e05
    classDef omitted fill:#f3f4f6,stroke:#6b7280,color:#111827,stroke-dasharray:2 3
    classDef evidenceDefault fill:#ffffff,stroke:#475569,color:#0f172a
    class N_0b51dce8fe915eda conflict
    class N_6f91af1641ed1424 supported
    class N_8575658723b5d49d supported
    class N_5522d8dace1cb6e7 conflict
    class N_ac65699e766edc85 unknown
    class N_ef4722a060cacfda verified
    class N_1ded0fae46344828 verified
    class N_c075a66077dd6940 verified
    class N_e824b2ad012b224e verified
    class N_a42d56cfe9dff13d verified
    class N_f797fb20a8448aa0 evidenceDefault
    class N_a17fb3165e6b0db5 evidenceDefault
    class N_6630b028247f1a08 evidenceDefault
    class N_2eb930959384d64c omitted
```
<!-- atlas-self-review-mermaid:end -->

## Community and trust

- Read [Security](SECURITY.md) before reporting sensitive evidence.
- Use [Support](SUPPORT.md) to choose the right channel.
- Review the [Roadmap](ROADMAP.md) and [Governance](GOVERNANCE.md).
- Contributions follow [CONTRIBUTING.md](CONTRIBUTING.md) and the
  [Code of Conduct](CODE_OF_CONDUCT.md).

If stale proof, bounded scope, or portable Agent evidence is a problem you want
to revisit, Star the repository as a bookmark—and, more importantly, try the
demo and report what did or did not reproduce.

MIT License.
