---
name: agent-engineering-toolkit
description: Compatibility entrypoint for AET Quick and advanced AET Lab workflows. Prefer the four dedicated Quick Skills for daily work; use this Skill only when the user explicitly asks for legacy CLI or Lab capabilities.
---

# Agent Engineering Toolkit

Current Skill version: `1.13.0` (Quick compatibility + opt-in Lab)

## Activation policy

**Default: OFF.** Installing this Skill does not authorize its use. Load or run
AET only when the user explicitly asks to use AET for the current task (for
example, “use AET”, “run `aet audit`”, or “produce an AET Evidence Pack”). A
repository containing AET files, a generic request to test/review a change, or
the availability of the `aet` executable is not opt-in. Do not carry opt-in
across tasks.

After explicit activation, choose only the smallest surface needed. Daily work
should route to `/aet-check`, `/aet-scope`, `/aet-proof`, or `/aet-fresh`.
Each Quick Skill emits one bounded result and stops. It never enters another
Quick Skill or AET Lab automatically.

Use the `aet` CLI as the source of truth. The host agent may choose its own
shell or package runner, but must preserve the commands' exit status and attach
the emitted evidence instead of paraphrasing it as unverified fact.

<!-- aet-learn:immutable -->
`UNKNOWN` is never a pass. Only `aet trace` executes explicit argv after `--`.
Audit, review, and Evidence Pack compilation stay deterministic and local. AET
may propose, replay, gate, and stage a Constitution-bound asset candidate, but
it never adopts a candidate, commits it, pushes it, or lowers an evidence contract automatically.
<!-- aet-learn:end -->

## Quick routes

This section applies only after explicit activation. Choose one initial surface.
If the requested AET surface is ambiguous, ask which claim needs evidence;
do not infer permission for a broader workflow.

| User need | Preferred Skill | Deterministic CLI |
| --- | --- | --- |
| Check Agent instructions and Skills | `/aet-check` | `aet quick check` |
| Investigate whether a diff fits the task | `/aet-scope` | `aet quick scope` |
| Execute and record one real verification | `/aet-proof` | `aet quick proof` |
| Check whether a proof still applies | `/aet-fresh` | `aet quick fresh` |

When a slash command and its question are both Chinese, the host explanation
uses natural Simplified Chinese while code and required technical terms remain
English. Every other request uses English.

## Advanced and Lab compatibility

The legacy `audit`, `review`, `trace`, Evidence Pack, Context, Decision,
Repository Audit Showcase, Evolve, Quality, Learn, Gate, Shadow, Stage, and
Adopt surfaces remain available for 1.x compatibility. They are not default
Quick routes. Load only the matching reference after the user explicitly asks
for that advanced capability.

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
