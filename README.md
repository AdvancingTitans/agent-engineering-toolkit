# Agent Engineering Toolkit

[![CI](https://github.com/AdvancingTitans/agent-engineering-toolkit/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/AdvancingTitans/agent-engineering-toolkit/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/AdvancingTitans/agent-engineering-toolkit?display_name=tag&sort=semver)](https://github.com/AdvancingTitans/agent-engineering-toolkit/releases)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)
[![中文](https://img.shields.io/badge/docs-%E4%B8%AD%E6%96%87-red)](docs/README.zh-CN.md)

**[English](README.md) · [简体中文](docs/README.zh-CN.md)**

> AET is the local evidence and control layer between agent work, delivery
> claims, and bounded improvement of the assets that govern that work.

**Agent Engineering Toolkit (AET)** makes coding-agent work inspectable before
it is trusted, and improvable only when the improvement is itself evidenced.
It records the instructions available to an agent, the human-approved change
boundary, explicit command execution, produced artifacts, and any verification
gap. Those records can travel with a delivery—or, when failures repeat, become
the input to a bounded evolution experiment for a registered governance asset.

This answers two different engineering questions with one evidence model:

| Question | AET answer |
| --- | --- |
| “Can we honestly say this agent delivery is ready?” | Audit instructions, review an approved diff, trace an explicit proof, and hand off the resulting evidence. |
| “Can this recurring failure improve the governing asset safely?” | Mine reproducible evidence, route it to a bounded target adapter, replay baseline and candidate with an independent evaluator, then require a human adoption decision. |

The important distinction is that AET is not a self-reporting layer. A natural
language answer never substitutes for a recorded command, artifact, snapshot,
or explicit `UNKNOWN` state.

## Why AET exists

Coding agents make it inexpensive to change a repository, but not necessarily
easy to answer the questions that matter at handoff: *Which instructions were
in scope? Was this command really run? Does the output still describe this
workspace? What is verified, and what remains unknown?*

They also do not make governance improve by itself. A repeated false negative,
misrouted proof workflow, or weak policy may be visible in production evidence,
yet changing the Skill or audit rule without an independent evaluator simply
moves the trust problem. AET exists to close both loops: evidence for the work,
and evidence for a bounded change to the assets governing the work.

Most teams solve fragments of this with chat transcripts, CI logs, prompt
edits, or manual checklists. AET gives those fragments a local, structured,
hash-bound form and keeps their meanings deliberately narrow. That makes the
system useful for ordinary delivery work today, without pretending that every
agent session should become training data tomorrow.

## Why AET

- **Evidence-first, not confidence-first.** `UNKNOWN` stays a verification gap;
  it is never discounted into a pass.
- **Smallest safe surface.** `audit` and `review` inspect; only `trace` executes
  the explicit argv after `--`.
- **Local by default.** Evidence collection, review, Experience Store, and
  federation do not require a hosted telemetry service or transcript archive.
- **Proof remains fresh-or-stale.** A successful command and a workspace that
  later changed are represented as separate facts.
- **Learning is constrained.** Candidate Skills and audit assets are bound to
  their baseline hash, bounded Patch IR, and Evolution Constitution; independent
  Gate evidence and an explicit human action are still required.
- **The evaluator follows the target.** Skills use static or opt-in real-host
  behavior replay; Audit Rules use deterministic fixtures and real-repository
  Shadow; bounded policies use policy-specific suites. A generic LLM judge does
  not decide adoption.
- **Production evidence cannot be gamed by the candidate.** The Constitution,
  evaluator, held-out cases, evidence-state meanings, and human-adoption rule
  are outside candidate authority.
- **Audit evolution has a real-world brake.** A fixture-passing Audit Rule still
  needs candidate-bound Shadow evidence, confirmed findings, and zero confirmed
  false positives before adoption.

AET is **not** an agent runtime, a general autonomous coding framework, a
hosted monitoring product, or a system that rewrites arbitrary production code.

## Core concepts

| Concept | Meaning in AET |
| --- | --- |
| **Evidence Plane** | `audit`, `review`, `trace`, `context`, `decision`, `evolve`, and `run` record narrow facts about instructions, intent, execution, artifacts, freshness, and history. |
| **Evidence Only** | Learning defaults to structured deviations and hashes, not raw transcripts, complete shell output, secrets, or an unbounded telemetry archive. |
| **Evidence-Gated Asset Evolution** | Repeated failures may produce a bounded candidate for one registered target; the candidate is replayed by an evaluator it cannot modify. |
| **Evolution Constitution** | Immutable cross-target rules: `UNKNOWN` is not PASS, held-out stays separate, candidates cannot change evaluators or evidence semantics, and adoption remains human-authorized. |
| **Stage vs. Adopt** | A passing candidate is copied for review. Only a later explicit `adopt --yes` may replace the hash-matching target and write a Decision Ledger record. |
| **Shadow Audit** | A candidate RulePack runs beside the official Audit. Its findings are private comparison evidence and never affect official output or exit code. |

## Start here

```bash
# Install the v1.8 release wheel, then verify it.
uv tool install https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/download/v1.8.0/agent_engineering_toolkit-1.8.0-py3-none-any.whl
aet --version

# Establish a baseline before an agent changes the repository.
aet init --output aet.toml
aet audit . --strict --format json --output .aet/evidence/audit.json
```

`aet audit` writes its JSON report even when it returns non-zero for a real
finding. Read that artifact first; a failed exit status means “the evidence
found a problem,” not “no audit JSON was produced.”

## Choose the smallest surface

| Question | Command | Result |
| --- | --- | --- |
| Are instructions, local references, and Skills usable? | `aet audit` | Markdown, JSON, or SARIF findings, versioned RulePack identity, evidence, and remediation; optional Profile and candidate Shadow. |
| Is a diff inside the human-approved contract? | `aet review` | Intent, path-budget, proof-declaration, and optional stricter Review Policy report. |
| Did an explicit command run and produce its declared report? | `aet trace -- <argv>` | Redacted execution record, fresh declared artifact, and optional safe validator result. |
| Can these records travel with a handoff or release? | `aet evidence pack` | Portable Evidence Pack and optional static Viewer. |
| Did a delivery become stale after review or proof? | `aet run` | Optional append-only delivery lifecycle. |
| What context and decisions were locally recorded? | `aet context`, `aet decision` | Hash-bound Context Manifest and Decision Ledger. |
| Why did this repository change? | `aet evolve` | Cited local/explicit-remote evolution report. |
| Which existing findings should be handled first? | `aet triage` | Explainable default or policy-driven ordering; never a changed finding status. |
| Can repeated failures improve a bounded asset safely? | `aet learn` | Evidence-only experience, target-specific candidate and Gate, optional Shadow evidence, and staged review copy. |

## Where AET fits

These tools are complementary. The comparison is about the job each one owns,
not a claim that one should replace the others.

| Tool category | Best used for | What AET adds or deliberately does not do |
| --- | --- | --- |
| Coding-agent runtime (Codex, Claude Code, Copilot) | Planning and executing the work in a repository. | AET does not replace the runtime; it records the local evidence needed to make its delivery claims reviewable. |
| CI, tests, linters, and security scanners | Checking code or a deployment against their own rules. | AET can trace an explicit check and bind its artifact to intent, workspace freshness, and a handoff; it does not replace the checker. |
| Skill authoring / governance system ([Yao Meta Skill](https://github.com/yaojingang/yao-meta-skill)) | Creating, packaging, compiling, evaluating, and governing reusable cross-platform Skill assets. | AET focuses on delivery evidence and independently gated improvement of in-use Skills and audit assets. Use Yao to engineer the Skill product; use AET to prove what happened and constrain what may evolve. |
| Skill optimizer ([SkillOpt](https://github.com/microsoft/SkillOpt)) | Training a Skill document from scored rollouts and held-out validation. | AET provides local engineering evidence semantics—intent boundaries, explicit command proof, artifact handling, freshness, and human adoption—rather than a general benchmark optimizer. |
| Transcript analytics / agent observability | Searching broad session history, dashboards, or fleet telemetry. | AET defaults to structured Evidence Only records and local storage; it intentionally does not ingest an unbounded transcript archive. |
| Policy engines (for example OPA) | Enforcing a broad, pre-authored policy language across systems. | AET is not a general policy engine. It evolves only six registered AET assets through monotonic, target-specific operations and evidence gates. |
| Evaluation frameworks / LLM judges | Measuring model or Agent quality across broad task sets. | AET evaluates engineering claims and bounded asset changes from commands, artifacts, diffs, fixtures, and explicit states; an LLM may propose, but never decides the Gate. |

### Choose AET when

- You need a credible handoff after an agent changed code: not just “tests passed,”
  but the command, exit status, declared artifact, approved scope, and freshness.
- You need to preserve the difference between **PASS**, **FAIL**, and
  **UNKNOWN** instead of collapsing uncertainty into a score.
- Repeated Agent behavior failures should improve a marked Skill region, with
  optional real Codex/Claude Code rollout rather than text matching presented as
  behavior evidence.
- Audit false negatives, false positives, wrong status/severity/location,
  incomplete remediation, duplicate findings, non-determinism, performance
  regressions, or requested policy exceptions need a reproducible fixture and
  an auditable Rule candidate.
- Different repository classes need stricter Audit Profiles or Review Policies,
  but a candidate must not disable rules, lower severity, expand scope, or remove
  proof requirements.
- JUnit, SARIF, coverage, or JSON artifacts need deterministic assertions bound
  to the exact Trace run that freshly created or changed them.
- Finding priority should adapt to critical paths without hiding findings or
  rewriting their original PASS/FAIL/UNKNOWN state.
- You need a local, portable evidence format that works alongside—not inside—an
  existing agent runtime and CI system.

### Do not choose AET as

- a replacement for writing tests, running CI, reviewing code, or securing a
  deployment;
- a substitute for an agent runtime or task planner;
- a promise that an Agent understood a file merely because it was discovered or
  attested as read; or
- an automatic self-modification daemon. `propose`, `gate`, `stage`, and
  `adopt` are intentionally separate actions.
- a way to generate or execute arbitrary Python audit plugins: Audit Rule
  candidates select only allowlisted, non-executable detectors; or
- proof that a released Audit Rule has accumulated real multi-repository Shadow
  evidence merely because the repository tests its Shadow threshold logic.

## Architecture

![Agent Engineering Toolkit architecture](docs/assets/aet-architecture-en.png)

<details>
<summary>Text-rendered Mermaid fallback</summary>

```mermaid
flowchart TB
  subgraph delivery["Delivery evidence plane"]
    A["Instructions + Skills"] --> B["audit\nstatic instruction facts"]
    C["Human intent + Git diff"] --> D["review\nscope and proof contract"]
    E["Explicit argv after --"] --> F["trace\nexecuted proof + declared artifacts"]
    G["Repository context + decisions"] --> H["context / decision / evolve\nhash-bound local history"]
    B --> I["Evidence IR\nstatus + hashes + workspace snapshots"]
    D --> I
    F --> I
    H --> I
    I --> J["Handoff\nEvidence Pack / Viewer / Run"]
  end

  subgraph learning["Optional evidence-gated evolution"]
    I -. "structured Evidence Only\nrepeated failures" .-> K["harvest + mine\npattern support"]
    K --> L["classify target\nSkill / rule / bounded policy"]
    L --> M["propose\nCandidate v2 + Constitution"]
    M --> S["Skill evaluator\nstatic or real-host rollout"]
    M --> R["Audit Rule evaluator\nfixture replay"]
    M --> U["Policy evaluator\ntarget-specific suite"]
    S --> N["independent Gate"]
    R --> N
    U --> N
    N --> O["stage\nhuman review copy"]
    O -. "Skill / Policy\nexplicit --yes" .-> P["adopt\nasset + Decision Ledger"]
    O --> V["Audit Rule Shadow\nreal repositories + confirmations"]
    V -. "threshold met +\nexplicit --yes" .-> P
    N -. "fail / inconclusive" .-> Q["reject record\nnegative constraint"]
  end

  P --> A
```

</details>

The learning path is deliberately optional. AET does not treat every artifact
as training data; static text checks are not presented as observed behavior;
and a passing Gate does not modify a production asset. Audit-rule adoption also
requires candidate-bound, adoption-grade Shadow evidence from real repositories.

## How to use AET

Start with the job, not the biggest workflow:

| If you need to… | Start with | Add only if needed |
| --- | --- | --- |
| Check whether an Agent’s local guidance is usable | `aet audit` | `context` when you need a hash-bound record of discovered/read assets. |
| Deliver an Agent-authored change | `audit` + `review` + `trace` | `evidence pack` for a portable handoff; `run` when the delivery has multiple lifecycle steps. |
| Explain why a repository looks this way | `aet evolve plan` | `collect/build/report` after reviewing the collection plan. |
| Improve recurring Agent behavior | `learn harvest` + `mine --target-type skill` | `propose/replay/gate/stage`; use a real host runner only when explicitly configured. |
| Improve an Audit false negative or false positive | `aet audit feedback record` | Mine as `audit-rule`, run four fixture partitions, then accumulate candidate-bound Shadow evidence. |
| Tighten Audit, Review, Trace, or Triage policy | `learn target list` | Supply a bounded JSON Patch, run the target-specific policy suites, stage, then explicitly adopt. |

### Recipe: evidence-backed delivery

```bash
# 1. Audit instructions and review the approved diff. Neither runs tests.
aet audit . --strict --format json --output .aet/evidence/audit.json
aet review . --base main --intent aet.intent.json --format json --output .aet/evidence/review.json

# 2. Execute exactly one declared proof through Trace.
aet trace --proof unit-tests --intent aet.intent.json \
  --artifact reports/junit.xml --output .aet/evidence/trace.json -- \
  python -m unittest discover -s tests -v

# 3. Compile a portable handoff receipt.
aet evidence pack --audit .aet/evidence/audit.json \
  --review .aet/evidence/review.json --trace .aet/evidence/trace.json \
  --output .aet/evidence/evidence-pack.json
aet evidence viewer --pack .aet/evidence/evidence-pack.json \
  --output .aet/evidence/evidence-viewer.html
```

Only `trace` executes a generic command, and only the argv after `--`. AET
keeps proof success separate from freshness: a trace may be valid while a later
workspace change makes the delivery stale. `UNKNOWN` is a verification gap,
never a discounted pass.

## Evidence-Gated Asset Evolution

v1.8 generalizes the existing Skill loop into target-specific evolution without
giving a candidate authority over its evaluator. Skills use static and opt-in
real-host evaluation. Declarative audit rules use deterministic fixtures plus
real-repository Shadow comparison. Bounded policies use independent policy
suites. The Evolution Constitution forbids candidates from changing evidence
semantics, evaluators, held-out data, or human-adoption requirements.

```text
Evidence Only JSON → inspect → mine → classify target → Candidate v2
→ target-specific replay → independent Gate → stage → human adopt/reject
```

### What can evolve today

| Target | Candidate boundary | Evaluator and adoption boundary |
| --- | --- | --- |
| `skill` | Named editable Markdown blocks | Static contract or opt-in Scripted/Codex/Claude Code paired rollout; only this target measures Agent behavior. |
| `audit-rule` | Versioned, non-executable RulePack over an allowlisted detector DSL | 70 partitioned tasks across 22 reusable fixtures; no FP/FN, determinism, or runtime regression; adoption additionally needs 20 confirmed Shadow runs across 5 repositories and 3 dates. |
| `audit-profile` | Rule severity, sensitive paths, and pre-approved exclusions; evolution cannot add exclusions | Deterministic policy suites; cannot disable a rule or lower severity. |
| `review-policy` | Sensitive paths and proof requirements may be added, not removed | Deterministic policy suites plus ordinary `review --policy`; it does not replace the Intent Contract. |
| `trace-validator` | Safe JUnit, SARIF, coverage, or JSON assertions | The file must be an explicitly declared artifact freshly created or changed by Trace; no generated Python or shell. |
| `triage-policy` | Weights and critical paths only | Ordering may change; original finding status and visibility may not. |

`aet learn target list` is the source of truth. The built-in automatic
audit-rule proposal currently covers a reproducible missing `package.json`
script target; the four policy targets require an explicit bounded JSON Patch.
This narrow proposal surface is intentional and auditable.

```bash
# Inspect the registered targets and record a reproducible audit deviation.
aet learn target list
aet audit feedback record --report .aet/evidence/audit.json \
  --finding AET-PKG-001 --outcome false-negative \
  --reason-code MISSING_PACKAGE_SCRIPT --fixture <minimal-fixture> \
  --output .aet/feedback/AFB-001.json

# Propose and gate a declarative Audit Rule against four separated partitions.
aet learn propose --target-type audit-rule --patterns .aet/learn/patterns.json \
  --target src/aet/rulepacks_builtin.json --output .aet/learn/candidates/CAND-001
aet learn gate --target-type audit-rule --candidate .aet/learn/candidates/CAND-001 \
  --core tests/evolution/audit/core/suite.json \
  --validation tests/evolution/audit/validation/suite.json \
  --held-out tests/evolution/audit/held_out/suite.json \
  --adversarial tests/evolution/audit/adversarial/suite.json \
  --output .aet/learn/gates/CAND-001.json

# Run the candidate beside the official audit. Shadow never changes official
# findings or the audit exit code.
aet audit . --shadow-rulepack .aet/learn/candidates/CAND-001/candidate.rulepack.json \
  --shadow-output .aet/shadow/run.json
aet learn shadow --reports .aet/shadow --confirmations .aet/shadow/confirmations.json \
  --output .aet/shadow/aggregate.json
```

An audit-rule Gate can stage a candidate, but adoption remains blocked until
the candidate-bound Shadow aggregate meets the 20-run / 5-repository / 3-date
threshold, every added finding is confirmed, and confirmed false positives are
zero. Even then, `aet learn adopt --yes --shadow-aggregate ...` is a separate
human action and writes a Decision Ledger record.

Runtime entry points for bounded policies are deliberately ordinary:

```bash
aet audit . --profile audit-profile.json
aet review . --policy review-policy.json
aet trace --artifact report.xml --validator-policy validator.json \
  --validate-artifact report.xml -- <argv>
aet triage --report audit.json --policy triage-policy.json
```

The real-host fixture is a proof-handoff smoke test, not a broad claim that
every task distribution is solved. For an adoption-grade observed Gate, bring
your own separated core, validation, and held-out tasks; configure sufficient
paired rollouts; and treat `INCONCLUSIVE` as a non-passing result.

```bash
# Phase 1: build and inspect a local Evidence Only experience set.
aet learn harvest --evidence .aet/evidence --output .aet/learn/experiences.json
aet learn inspect --experiences .aet/learn/experiences.json --output .aet/learn/inspection.json
aet learn mine --experiences .aet/learn/experiences.json --output .aet/learn/patterns.json

# Phase 2–3: propose and test only an editable Skill block.
aet learn propose --engine rules --patterns .aet/learn/patterns.json \
  --target skills/agent-engineering-toolkit/SKILL.md --output .aet/learn/candidates/CAND-001
aet learn replay --candidate .aet/learn/candidates/CAND-001 \
  --suite eval/core --suite eval/validation --suite eval/held-out \
  --output .aet/learn/replays/CAND-001.json
aet learn gate --candidate .aet/learn/candidates/CAND-001 --core eval/core \
  --validation eval/validation --held-out eval/held-out \
  --output .aet/learn/gates/CAND-001.json
aet learn viewer --gate .aet/learn/gates/CAND-001.json --output .aet/learn/CAND-001.html
aet learn stage --candidate .aet/learn/candidates/CAND-001 \
  --gate .aet/learn/gates/CAND-001.json --output .aet/learn/staged
```

The Gate rejects changed immutable bytes, edits outside named blocks, invalid
hashes, overlapping validation/held-out tasks, candidate audit failures,
regressions, token/command-surface budget breaches, and increased workflow
overuse. It reports a metric vector rather than one “trust” number.

`aet learn adopt --yes` is intentionally separate: it rechecks the target hash
and writes a local Decision Ledger record. `reject` preserves a reason. Neither
command commits or pushes.

### Real-host evaluation (opt-in)

The static runner is deliberately not an Agent-behavior claim. Use a real host
only when explicitly named; every baseline/candidate run receives an independent
fixture copy and writes private raw outputs plus public structured events,
before/after snapshots, scores, and hashes. `UNKNOWN` and host failures never
become a pass.

```bash
# Discover installed adapters without contacting a model.
aet learn runner list

# Run actual host behavior. Create a local `runner.json` containing
# `{"aet_argv": ["/absolute/path/to/aet"], "inherit_home": true}`;
# raw host output stays inside the rollout directory.
aet learn replay --candidate .aet/learn/candidates/CAND-001 \
  --suite eval/real-agent/core --runner codex --rollouts 3 \
  --runner-config runner.json --output .aet/learn/replays/CAND-001

# Only an adoptable profile can produce an observed PASS. A small sample is
# INCONCLUSIVE rather than a pass, and stage/adopt remain separate.
aet learn gate --candidate .aet/learn/candidates/CAND-001 \
  --core <core-suite> --validation <validation-suite> \
  --held-out <held-out-suite> --runner codex --rollouts 6 \
  --statistics-profile adoptable --runner-config runner.json \
  --output .aet/learn/gates/CAND-001-observed.json
```

`runner.json` is local configuration, not a credential store. Codex and Claude
Code adapters report `network_isolation: PARTIAL`: an isolated workspace protects
the production checkout, but neither host CLI is claimed to provide OS-level
network denial or command allowlisting. A host startup/auth/model failure is an
`INFRASTRUCTURE_ERROR`, not an Agent failure. The included
`eval/real-agent/core` fixture is a real proof-handoff smoke test; expand and
rotate validation/held-out suites before using an observed Gate for adoption.

### Local cross-project learning and scheduled use

```bash
# Explicitly share only local, de-identified Evidence Only packs.
aet learn collect --experiences .aet/learn/experiences.json --store ~/.aet/experience
aet learn harvest --experience-store ~/.aet/experience --output .aet/learn/merged.json

# A scheduler may invoke this bounded, stage-only local loop.
aet learn sleep --evidence .aet/evidence --target skills/agent-engineering-toolkit/SKILL.md \
  --core eval/core --validation eval/validation --held-out eval/held-out \
  --max-candidates 1 --max-replays 2 --max-model-calls 1 --timeout-seconds 120 \
  --output .aet/learn/nightly
```

No transcript, shell output, environment variable, secret, remote upload,
automatic commit, push, or adoption is part of the default. See the exact
[evolution boundary](docs/evolution-boundary.md).

## Context, decisions, and history

```bash
# Context discovery records file bytes; --read is only an agent/host attestation.
aet context discover . --output .aet/context/manifest.json
aet context record --manifest .aet/context/manifest.json --read AGENTS.md
aet context verify --manifest .aet/context/manifest.json

# Decision records are local, source-backed, and verifiable later.
aet decision init --output .aet/decisions.json
aet decision add --ledger .aet/decisions.json --id DEC-0001 \
  --claim "Keep proof execution explicit." --evidence-state EVIDENCED \
  --source docs/evolution-boundary.md
aet decision verify --ledger .aet/decisions.json

# Repository archaeology is offline unless --remote github is explicit.
aet evolve plan . --question "Why was this release made?" --output .aet/evolve/plan.json
aet evolve collect . --question "Why was this release made?" --output .aet/evolve/run
aet evolve build --manifest .aet/evolve/run/source-manifest.json --output .aet/evolve/run
aet evolve report --graph .aet/evolve/run/object-graph.json --output .aet/evolve/run
```

## Installing the portable Skill

Copy the entire [`skills/agent-engineering-toolkit/`](skills/agent-engineering-toolkit/)
directory into the host’s Skill directory; do not copy only `SKILL.md` if you
want its referenced contracts too.

```bash
# From a source checkout of this repository (the wheel ships the CLI, not Skill assets):
git clone https://github.com/AdvancingTitans/agent-engineering-toolkit.git
cd agent-engineering-toolkit
cp -R skills/agent-engineering-toolkit ~/.codex/skills/
aet audit ~/.codex --format json --output ~/.aet/evidence/codex-audit.json
```

For a migrated Hermes installation, AET keeps a missing old Skill reference as
a `FAIL` but, when Hermes’s `.absorbed_into` metadata identifies a real local
replacement, includes that replacement in remediation. This is intentional:
the old instruction still needs repair, but the report explains the migration
instead of leaving an opaque path failure.

## Verification and limits

Run the project checks from a source checkout:

```bash
uv run --no-editable --reinstall-package agent-engineering-toolkit \
  python -m unittest discover -s tests -v
uv run --no-editable --reinstall-package agent-engineering-toolkit \
  aet audit . --strict --format json --output .aet/evidence/self-audit.json
uv build
```

AET verifies recorded bytes, explicit command exits, and declared artifact
handling. It does not prove a model understood an instruction, that a decision
is eternally correct, that an untraced command ran, or that a missing remote
record supports a claim. Read [the rule catalog](docs/rule-catalog.md) and
[security and retention boundary](docs/security-and-retention.md) before
relying on it in a regulated workflow.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Changes to evidence semantics require
tests, a clear contract update, and a human-reviewed intent boundary.
