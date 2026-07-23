---
name: agent-engineering-toolkit
description: Opt-in AET quality controls for evidence-backed Agent delivery and governance-asset evolution. Use only when the user explicitly asks to use AET for the current task; never auto-enable for ordinary coding, review, testing, or repository work.
---

# Agent Engineering Toolkit

Current Skill version: `1.12.0` (Evidence → Quality → conditional Gate → bounded Evolution)

## Activation policy

**Default: OFF.** Installing this Skill does not authorize its use. Load or run
AET only when the user explicitly asks to use AET for the current task (for
example, “use AET”, “run `aet audit`”, or “produce an AET Evidence Pack”). A
repository containing AET files, a generic request to test/review a change, or
the availability of the `aet` executable is not opt-in. Do not carry opt-in
across tasks.

After explicit activation, choose only the smallest surface needed. Prefer
`aet evidence receipt` when a compact status is sufficient. A successful Trace
may be reused only through explicit `aet trace --reuse-if-fresh`, which refuses
command, proof, artifact, log, or workspace drift without executing anything.
Do not run
real-host replay, Gate, tournament, or Sleep unless the user separately asks
for governance-asset evaluation or evolution. Do not repeat a proof command
that already has fresh, hash-bound evidence for the unchanged workspace.

Use the `aet` CLI as the source of truth. The host agent may choose its own
shell or package runner, but must preserve the commands' exit status and attach
the emitted evidence instead of paraphrasing it as unverified fact.

<!-- aet-learn:immutable -->
`UNKNOWN` is never a pass. Only `aet trace` executes explicit argv after `--`.
Audit, review, and Evidence Pack compilation stay deterministic and local. AET
may propose, replay, gate, and stage a Constitution-bound asset candidate, but
it never adopts a candidate, commits it, pushes it, or lowers an evidence contract automatically.
<!-- aet-learn:end -->

## Route the request

This section applies only after explicit activation. Choose one initial surface.
If the requested AET surface is ambiguous, ask which claim needs evidence;
do not infer permission for a broader workflow.

| User need | Initial command | Output |
| --- | --- | --- |
| Trust current instructions / Skills | `aet audit . --strict` | Audit report |
| Inspect a commit-locked public Agent repository case | `aet audit <case> --repo <checkout>` | 12-file bilingual static Showcase bundle |
| Check a proposed or completed diff | `aet review . --base <base>` | Review report |
| Prove a command ran and retain a declared text report | `aet trace --proof <id> --artifact <path> … -- <argv>` | Trace + pack |
| Understand why a repo changed | `aet evolve plan/collect/build/report` | Evolution Pack |
| Record which local context was available | `aet context discover/record/verify` | Context Manifest |
| Preserve a source-backed project decision | `aet decision init/add/verify` | Decision Ledger |
| Map structured failures to an owner and repair surface | `aet quality diagnose` | Deterministic diagnosis; source status is unchanged |
| Stage a confirmed badcase as a regression candidate | `aet quality promote` | Validation-only Task v2 bundle for human review |
| Improve a bounded Skill or audit asset | `aet learn target list`, then `harvest/inspect/mine/propose/replay/gate/stage` | Staged candidate + target-specific Gate report |

Repo Archaeologist example: “Explain why this repository adopted a plugin architecture; link releases, PRs, Issues, commits, and README changes, and separate direct evidence from candidates.” Use `aet evolve`; never invent author intent.

## Load one workflow reference

After routing, load only the matching reference; do not preload the whole AET
manual into the Agent context.

| Surface | Read only when needed |
| --- | --- |
| Audit, Review, Trace, Pack, Run | [delivery workflow](references/delivery-workflow.md) |
| Repository Audit Showcase | [repository audit showcase](references/repository-audit-showcase.md) |
| Context, Decision, Evolve | [provenance workflow](references/provenance-workflow.md) |
| Quality diagnose/promote | [quality workflow](references/quality-workflow.md) |
| Learn, real-host Gate, Stage/Adopt | [evolution workflow](references/evolution-workflow.md) |
| Runner, privacy and trust boundaries | [security boundaries](references/security-boundaries.md) |

<!-- aet-learn:editable id="routing-guidance" -->
For repeated Evidence Only failures, use `harvest → inspect → mine → propose`.
For observed behavior, freeze `aet learn plan` before any rollout, then pass the
exact plan to `aet learn gate --gate-plan <plan.json>`. Use `--resume` only for
an exact observed replay binding. Gate may stop on a hard regression or a
pre-registered statistical boundary; history is planning-only and never enters
PASS. Stage remains human review, and only explicit `adopt --yes` may write the
target. Never auto-adopt, commit, push, release, or treat `INCONCLUSIVE` as PASS.
<!-- aet-learn:end -->

## Portable use

This folder is the canonical, tool-neutral Skill. Install or load the complete
folder in any host that supports `SKILL.md` folders. If the host has no native
Skill loader, place this file in that agent's project instructions and ensure
the `aet` executable is available. The optional `agents/` metadata is
OpenAI-specific UI metadata; other hosts may ignore it.

For compatibility rules and output contracts, read only when the chosen route requires them:
[cross-agent use](references/cross-agent-use.md), then the applicable
[audit contract](references/v0.1-contract.md),
[review contract](references/v0.2-contract.md), or
[Evidence Pack and Trace contract](references/v0.3-contract.md), then the [v1 product contract](references/v1-contract.md).

The immutable boundary above always applies. Detailed runner and privacy rules
live in [security boundaries](references/security-boundaries.md). AET is not a
general benchmark, LLM-Judge platform, semantic RCA engine, auto-repair daemon,
release bot, or online ticket/metrics platform.
