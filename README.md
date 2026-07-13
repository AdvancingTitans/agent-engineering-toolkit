# Agent Engineering Toolkit

[![CI](https://github.com/AdvancingTitans/agent-engineering-toolkit/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/AdvancingTitans/agent-engineering-toolkit/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/AdvancingTitans/agent-engineering-toolkit?display_name=tag&sort=semver)](https://github.com/AdvancingTitans/agent-engineering-toolkit/releases)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)
[![中文](https://img.shields.io/badge/docs-%E4%B8%AD%E6%96%87-red)](docs/README.zh-CN.md)

**[English](README.md) · [简体中文](docs/README.zh-CN.md)**

> **The evidence-driven control plane for Agent-engineered repositories.**

Agents can write code, call tools, and claim success. AET answers the harder
engineering questions: **what actually happened, what may be claimed, what
remains unknown, what failed, what may evolve, and who is allowed to approve
the change.**

AET sits between an external Agent runtime and production trust. It turns
commands, diffs, artifacts, instructions, workspace state, and human intent
into hash-bound evidence; converts confirmed failures into bounded quality
assets; and tests governance changes with evaluators the candidate cannot
modify.

```text
External execution → Evidence IR → Deterministic Quality → Bounded Evolution
                   → Independent Gates → Human Adoption
```

It is not another Agent runtime or score dashboard. It is the engineering layer
that makes Agent work **inspectable before release and improvable without giving
the optimizer authority over the judge**.

## The result, not the promise

The v1.9 release was gated with real Codex CLI `0.144.1` behavior on three
byte-separated suites. Each suite used six paired baseline/candidate rollouts.

| Real-host release gate | Baseline | Bounded candidate | Absolute gain | Infra failures | Exact paired p |
| --- | ---: | ---: | ---: | ---: | ---: |
| Core | 0 / 6 | **6 / 6** | +100 pp | 0 | 0.03125 |
| Validation | 0 / 6 | **6 / 6** | +100 pp | 0 | 0.03125 |
| Held-out | 0 / 6 | **6 / 6** | +100 pp | 0 | 0.03125 |
| **Continuous success** | **0 / 18** | **18 / 18** | **+100 pp** | **0** | — |

Every successful candidate rollout used exactly one authorized `aet trace`
command. The candidate remained inside a 676-character edit budget, could not
modify the Task suites or evaluator, and still required human adoption.

This is an AET release-gate case study—not a claim that one small task proves
general model superiority. It demonstrates the property AET is designed to
provide: **a governance asset can improve real Agent behavior under isolated,
statistical, provenance-bound and human-controlled evaluation.** The tracked
suites and producer are in [`eval/real-agent`](eval/real-agent) and
[the real-host workflow](.github/workflows/real-host-gate.yml).

## Why AET is different

Most Agent quality stacks start with a transcript or a score. AET starts with
the trust boundary.

| Engineering concern | A common shortcut | AET's contract |
| --- | --- | --- |
| Proof | The Agent says “tests passed.” | `trace` records the exact argv, exit code, logs, declared artifacts and proof binding. |
| Freshness | A passing log is treated as permanently valid. | Proof success and current workspace freshness are separate facts. |
| Uncertainty | Missing evidence is folded into a score. | `UNKNOWN` remains a first-class, release-blocking verification gap. |
| Diagnosis | A model guesses the root cause. | Explicit policies map observed phenomena to bounded owners and repair surfaces without rewriting source status. |
| Improvement | The candidate edits its prompt and judges itself. | Candidate writes, evaluator bytes, held-out suites, evidence semantics and adoption authority are separated. |
| Reliability | One successful run is enough. | any-success, all-success, Wilson 95% intervals and paired exact McNemar are reported together. |
| Privacy | Raw transcripts become the default data lake. | Raw rollout output stays private; only de-identified Evidence Only records may travel. |
| Authority | A passing optimizer deploys its own change. | Gate → stage → human review → explicit `adopt --yes`; never auto-commit, push or release. |

The design is deliberately asymmetric: the Agent may act, but it cannot grant
itself evidence, redefine `PASS`, replace the evaluator, or authorize adoption.

## Architecture

![AET evidence-driven Agent engineering control plane](docs/assets/aet-architecture-en.png)

Editable, offline source: [English HTML](docs/assets/aet-architecture-en.html) ·
[Chinese HTML](docs/assets/aet-architecture-zh-cn.html).

The architecture has five cooperating stages and one non-negotiable authority
boundary:

1. **Evidence Plane — capture facts.** `audit`, `review`, `trace`, `context`,
   `decision`, `run` and `evolve` record narrow, hash-bound facts. Only `trace`
   executes, and only the argv after `--`.
2. **Deterministic Quality — explain without guessing.** `quality diagnose`
   applies an explicit local mapping; `quality promote` can stage only a
   confirmed, de-identified, validation-only regression candidate.
3. **Bounded Evolution — propose inside a Constitution.** Evidence Only
   patterns are routed through one registered target adapter and a bounded
   Patch IR. Immutable evaluator and evidence semantics stay outside the write
   surface.
4. **Independent Gates — prove behavior, not prose.** Core, validation,
   held-out, adversarial, policy and Shadow suites are selected by target type.
   Real-host evaluation is opt-in and repeated.
5. **Human Adoption — retain authority.** A passing Gate produces a reviewable
   stage. Adoption rechecks the baseline hash and requires explicit human
   authorization, writing the result to the Decision Ledger.

The output is not merely a report. It is a growing set of reusable engineering
assets: Evidence Packs, regression candidates, diagnosis records, Gate and
Shadow evidence, rejection memory, Context Manifests, Run Manifests and
Decision Ledger entries.

## Product surfaces

Start with the smallest surface that answers the question.

| Question | Command | What it establishes |
| --- | --- | --- |
| Are the Agent's instructions and Skills structurally usable? | `aet audit` | Deterministic findings, source evidence, RulePack identity and remediation. |
| Is this diff inside the human-approved change contract? | `aet review` | Intent, path budget, proof declarations and optional Review Policy. |
| Did this exact proof command run and produce this artifact? | `aet trace -- <argv>` | Command, exit status, logs, artifacts, redaction and workspace snapshot. |
| Can the evidence travel with a handoff? | `aet evidence pack` | Portable Evidence Pack and optional static Viewer. |
| Did the repository change after the proof? | `aet run verify` | Fresh, stale or explicitly unknown lifecycle state. |
| What context and decisions were actually recorded? | `aet context`, `aet decision` | Hash-bound manifests and source-backed project memory. |
| Why did this repository evolve this way? | `aet evolve` | Cited local/explicit-remote archaeology, not invented author intent. |
| Which bounded route matches a structured failure? | `aet quality diagnose` | Status-preserving owner/action/repair mapping and review routing. |
| Can a confirmed failure become a regression asset? | `aet quality promote` | Validation-only Task v2 staging bundle; no production write. |
| Can recurring failures improve a governance asset? | `aet learn` | Evidence Only mining, target-specific replay/Gate, stage and human adoption. |

## Quick start: trustworthy delivery

Install the current release:

```bash
uv tool install https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/download/v1.9.0/agent_engineering_toolkit-1.9.0-py3-none-any.whl
aet --version
```

Create a reviewable contract, audit the instructions, review the diff, and run
the declared proof through Trace:

```bash
aet init --output aet.toml

aet audit . --strict --format json \
  --output .aet/evidence/audit.json

aet review . --base main --intent aet.intent.json --format json \
  --output .aet/evidence/review.json

aet trace --proof unit-tests --intent aet.intent.json \
  --artifact reports/pytest.txt \
  --output .aet/evidence/trace.json \
  -- python -m pytest -q

aet evidence pack \
  --audit .aet/evidence/audit.json \
  --review .aet/evidence/review.json \
  --trace .aet/evidence/trace.json \
  --output .aet/evidence/evidence-pack.json
```

`audit` and `review` never execute a declared proof. A non-zero Audit exit still
writes its report; inspect the finding before deciding what to fix. Trace is
opt-in, rejects unsafe artifact paths, independently redacts declared UTF-8
artifacts, and preserves a successful child exit separately from an artifact
verification gap.

## From badcase to regression asset

Quality is deterministic before it becomes generative:

```bash
aet quality diagnose \
  --report .aet/evidence/failure.json \
  --policy quality-mapping.json \
  --output .aet/quality/diagnosis.json

aet quality promote \
  --badcase confirmed-badcase.json \
  --diagnosis .aet/quality/diagnosis.json \
  --policy quality-mapping.json \
  --output .aet/quality/staged-regressions
```

Diagnosis is explicit policy lookup, not semantic RCA. Promotion is intentionally
narrow: the sample must be confirmed, reproducible, de-identified,
representative and non-duplicate. It writes a content-addressed validation
candidate and provenance sidecar—not a production Skill, test suite, ticket or
auto-fix.

## Evidence-gated evolution

AET can evolve six registered governance targets:

| Target | Candidate surface | Evaluator | Additional brake |
| --- | --- | --- | --- |
| Skill | Marked editable block | Static contract or real Codex/Claude behavior | Paired statistics + human adoption |
| Audit Rule | Declarative, non-executable detector selection | Core / validation / held-out / adversarial fixtures | Adoption-grade multi-repository Shadow |
| Audit Profile | Monotonic configuration | Target-specific policy suite | Cannot disable rules or lower severity |
| Review Policy | Bounded JSON Patch | Review-policy suite | Cannot expand scope or remove proof |
| Trace Validator | Allowlisted validator policy | Validator suite | Cannot weaken evidence semantics |
| Triage Policy | Ordering policy | Triage suite | May reorder; never hide or rewrite findings |

The standard loop is explicit and separable:

```bash
aet learn harvest --evidence .aet/evidence \
  --output .aet/learn/experiences.json
aet learn mine --experiences .aet/learn/experiences.json \
  --target-type skill --output .aet/learn/patterns.json
aet learn propose --engine rules --patterns .aet/learn/patterns.json \
  --target skills/agent-engineering-toolkit/SKILL.md \
  --output .aet/learn/candidates/CAND-001

aet learn gate --candidate .aet/learn/candidates/CAND-001 \
  --core eval/core --validation eval/validation --held-out eval/held-out \
  --output .aet/learn/gates/CAND-001.json

aet learn stage --candidate .aet/learn/candidates/CAND-001 \
  --gate .aet/learn/gates/CAND-001.json \
  --output .aet/learn/staged
```

`stage` is not adoption. `adopt --yes` rechecks immutable bytes and the target's
current hash. AET never schedules itself, uploads a transcript, opens a ticket,
commits, pushes or publishes a release.

### Real-host evaluation

Static replay checks document contracts; it is never presented as observed
Agent behavior. Name a real runner when behavior matters:

```bash
aet learn runner list

aet learn replay --candidate .aet/learn/candidates/CAND-001 \
  --suite eval/real-agent/core --runner codex --rollouts 3 \
  --runner-config runner.json \
  --output .aet/learn/replays/CAND-001

aet learn gate --candidate .aet/learn/candidates/CAND-001 \
  --core eval/real-agent/core \
  --validation eval/real-agent/validation \
  --held-out eval/real-agent/held-out \
  --runner codex --rollouts 6 --statistics-profile adoptable \
  --runner-config runner.json \
  --output .aet/learn/gates/CAND-001.json
```

Host startup, authentication failure, timeout, empty structured events and
unsupported isolation remain `INFRASTRUCTURE_ERROR`, `UNKNOWN` or
`INCONCLUSIVE`; they never become a candidate pass. Raw outputs and normalized
events stay inside private rollout directories. Only derived Evidence Only
phenomena, scores and hashes are eligible for export.

## Where AET fits

AET complements existing tools instead of pretending to replace them.

| Tool category | It owns | AET owns |
| --- | --- | --- |
| Codex, Claude Code, Copilot and other runtimes | Planning and executing repository work | Evidence and authority around the runtime's delivery claims |
| Tests, CI, linters and security scanners | Domain-specific checks | Exact execution proof, artifact binding, intent and freshness around those checks |
| LangSmith, Braintrust, DeepEval and observability stacks | Broad experiment, trace and fleet analytics | Local engineering evidence semantics and bounded governance-asset adoption |
| OPA and policy engines | General pre-authored policy enforcement | AET-specific monotonic policies and evidence-gated evolution |
| Skill authoring and optimization systems | Creating or training Skill content | Proving in-use behavior and constraining what may be evaluated, staged and adopted |
| Ticketing and business dashboards | Operational workflow and online outcome tracking | Structured local evidence that those systems may consume |

Choose AET when a coding-agent handoff needs more than “looks good,” when
`FAIL` and `UNKNOWN` must remain different, or when a recurring failure should
improve a governance asset without giving the candidate control of its own
evaluation.

Do not choose AET as an Agent runtime, general benchmark, LLM-Judge center,
automatic semantic RCA/Evidence Graph, clustering platform, Skill quality-YAML
standard, hosted transcript service, business dashboard or autonomous release
bot.

## Security and trust boundaries

- **Only Trace executes.** `audit`, `review`, quality diagnosis, Evidence Pack
  compilation and deterministic replay are read-only with respect to the proof
  command.
- **Trace evidence is independently checked.** The scorer binds the trusted
  wrapper, outer child argv, Trace argv, Intent proof command, artifacts, logs,
  redaction rules and before/after snapshots. Command-shaped text is not proof.
- **Fixtures are copied without following links.** Nested symlinks, special
  files, outside-root sources and post-copy hash drift are rejected.
- **Environment permission is explicit.** A Task names allowed environment
  variables; process runners also require `inherit_home: true` for `HOME`.
  Authorization to inherit a value never authorizes exporting it.
- **Network posture is truthful.** A runner that cannot enforce OS-level denial
  reports `PARTIAL`; an `enforced-deny` Task fails before execution.
- **Candidate authority is bounded.** Evaluator code, held-out cases,
  Constitution, evidence states and human adoption are immutable to the
  candidate.

These controls reduce the candidate's influence. They do not claim an
impossible-to-game evaluator, perfect sandbox, or proof that a model understood
every discovered instruction.

## Portable Skill and repository archaeology

The canonical tool-neutral Skill lives in
[`skills/agent-engineering-toolkit`](skills/agent-engineering-toolkit). The
wheel contains the CLI, not the Skill resources. From a source checkout, copy
the complete directory rather than only `SKILL.md`:

```bash
git clone https://github.com/AdvancingTitans/agent-engineering-toolkit.git
cd agent-engineering-toolkit
cp -R skills/agent-engineering-toolkit ~/.codex/skills/
aet audit ~/.codex --format json --output ~/.aet/evidence/codex-audit.json
```

For source-backed project history, `aet evolve plan/collect/build/report`
collects local Git and documentation by default. GitHub access occurs only with
explicit `--remote github`. Missing remote evidence stays `UNKNOWN`; AET never
invents author intent from commit text alone.

## Verification

The release itself leaves runnable checks behind:

```bash
uv run --with pytest python -m pytest -q
uv run --with pytest python -m pytest tests/test_business_quality_flows.py -q
uv run --no-editable --reinstall-package agent-engineering-toolkit \
  aet audit . --strict --format json --output .aet/evidence/release-audit.json
uv build
uv run --isolated --with dist/agent_engineering_toolkit-1.9.0-py3-none-any.whl \
  aet --version
```

See [CHANGELOG.md](CHANGELOG.md), the
[evolution boundary](docs/evolution-boundary.md), and the
[v1.9 implementation plan](docs/superpowers/plans/2026-07-13-v1-9-quality-loop.md)
for the detailed contracts behind the architecture.

## Contributing

Issues and pull requests are welcome. Preserve the defining constraints:
deterministic checks before model judgment, explicit `UNKNOWN`, candidate and
evaluator separation, private raw evidence, target-specific Gates, and human
authority over adoption.

Released under the [MIT License](LICENSE).
