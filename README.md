# Agent Engineering Toolkit

[![CI](https://github.com/AdvancingTitans/agent-engineering-toolkit/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/AdvancingTitans/agent-engineering-toolkit/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/AdvancingTitans/agent-engineering-toolkit?display_name=tag&sort=semver)](https://github.com/AdvancingTitans/agent-engineering-toolkit/releases)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-3776AB)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/license-MIT-2ea44f)](LICENSE)
[![Docs: 中文](https://img.shields.io/badge/docs-%E4%B8%AD%E6%96%87-red)](docs/README.zh-CN.md)

**[English](README.md) · [简体中文](docs/README.zh-CN.md)**

> Coding agents move quickly. AET makes their engineering evidence move with them.

**Agent Engineering Toolkit (AET)** is an evidence-first, local CLI and portable
Agent Skill for coding-agent work. It checks the instructions an agent reads,
the change boundary a human approved, the command that actually ran, and the
repository history behind a decision—without turning missing proof into a
comforting score. In v1.5 it can also turn recurring, structured evidence into
a **bounded Skill-improvement proposal**, then prove the proposal is safe on
separate evaluation tasks before a human decides whether to adopt it.

Use it before an agent changes a repository, at handoff or release time, or
when you need a cited answer to “why is this repository built this way?”

[Quick start](#quick-start) · [Capability surface](#capability-surface) · [Evidence-Gated Evolution](#evidence-gated-evolution-v15) · [Context & decisions](#context-and-decisions-local-provenance-not-agent-memory) · [Quality](#quality-and-current-results) · [Repo Archaeologist](#repo-archaeologist) · [Contributing](CONTRIBUTING.md)

## Why AET, and why now?

Coding agents can produce a clean diff while still following stale instructions,
going outside an approved scope, or presenting an unrun command as proof. Git
history can show *what* changed but rarely connects releases, documentation,
issues, and commits in a reviewable way.

AET is the small, deterministic layer between agent work and a claim of
readiness. It does not replace tests, security scanners, code review, or an
agent runtime. It gives those processes a portable receipt: what was inspected,
what was declared, what was explicitly executed, and what remains unknown.

## Capability surface

| Question | AET surface | What you receive |
| --- | --- | --- |
| Can this agent safely follow the repository instructions and Skills? | `aet audit` | Markdown, JSON, or SARIF findings with locations and fixes. |
| Is the diff inside the human-approved intent? | `aet review` | An intent-gate report for path budget, allowed paths, and declared proofs. |
| Did the command run against the reviewed workspace, and did it produce its declared test report? | `aet trace --artifact` + `aet evidence pack` | A redacted execution record, explicitly captured report, plus proof and workspace-snapshot bindings. |
| What delivery stage is this evidence chain in, and did it become stale? | `aet run` | An optional append-only Run Manifest with explicit lifecycle states. |
| Which local instructions/references were available, and what was only claimed as read? | `aet context` | A hash-bound Context Manifest; read declarations are explicit attestations. |
| Which project decisions have local sources, and which records supersede them? | `aet decision` | A source-hash Decision Ledger with verification and supersession history. |
| Why did the repository evolve this way? | `aet evolve` | An Evolution Pack, timeline, decision index, and cited report. |
| What should be fixed first? | `aet triage` | Transparent priority ordering; it never changes a finding status. |
| Can repeated, evidenced failures improve the Agent Skill without silently weakening it? | `aet learn` | A bounded candidate, isolated replay, Gate report, and optional human-reviewed staged copy. |

### A Skill, not just another CLI

The portable Skill in [`skills/agent-engineering-toolkit/`](skills/agent-engineering-toolkit/)
teaches Codex, Claude Code, Cursor, Copilot-compatible hosts, and other
skill-aware agents to choose the smallest safe AET workflow: **audit, review,
evidence, or evolve**. The CLI remains the deterministic runtime and the JSON
artifacts remain portable when a host has no native Skill loader.

## Architecture

```mermaid
flowchart LR
  A["Agent instructions\nand Skills"] --> B["audit\nstatic hygiene"]
  C["Human intent\n+ Git diff"] --> D["review\nchange boundary"]
  E["Explicit argv\nafter --"] --> F["trace\nredacted execution"]
  G["Git, docs, releases,\nIssues, PRs"] --> H["evolve\nRepo Archaeologist"]
  B --> I["Evidence IR\nstatus + source hashes"]
  D --> I
  F --> I
  H --> J["Evolution Pack\nlinks + citations"]
  I --> L["learn\npattern → bounded candidate → gate"]
  L --> K
  I --> K["Reviewer, CI,\nor agent handoff"]
  J --> K
```

The four primary surfaces are independent. An offline `audit` does not fetch
GitHub data; `review` never executes a proof command; only `trace` executes
the exact argv placed after `--`; and `evolve --remote github` is explicit.
That separation keeps a useful report from quietly claiming more than its
evidence supports.

## Evidence-Gated Evolution (v1.5)

AET is not an “agent that edits itself.” It is an evidence system that can
learn from repeated engineering failures while preserving the boundaries that
make its reports trustworthy:

```text
structured AET evidence → failure pattern → bounded candidate → isolated replay
→ immutable/core/held-out gate → stage → human adopt or reject
```

The default is **Evidence Only**: it reads local AET JSON records, findings,
hashes, snapshots, and explicit rejection reasons—not raw conversations, shell
output, environment variables, or secrets. It never uploads experience data.
The model-assisted proposal adapter is opt-in, uses an explicit local command,
and can only return bounded Patch IR; it cannot decide a gate or adopt a Skill.

```bash
# Phase 1–3: local evidence becomes a bounded proposal.
aet learn harvest --evidence .aet/evidence --output .aet/learn/experiences.json
aet learn mine --experiences .aet/learn/experiences.json --output .aet/learn/patterns.json
aet learn propose --engine rules --patterns .aet/learn/patterns.json \
  --target skills/agent-engineering-toolkit/SKILL.md --output .aet/learn/candidates/CAND-001

# Phase 3–6: isolated replay and independent gates. Passing only stages it.
aet learn gate --candidate .aet/learn/candidates/CAND-001 --core eval/core \
  --validation eval/validation --held-out eval/held-out --output .aet/learn/gates/CAND-001.json
aet learn stage --candidate .aet/learn/candidates/CAND-001 \
  --gate .aet/learn/gates/CAND-001.json --output .aet/learn/staged
```

`aet learn adopt --yes` is deliberately separate and rechecks the target hash
before writing it, then records the adoption in the local Decision Ledger.
`aet learn reject` records why a proposal was declined. `aet learn sleep` can
run the bounded local sequence on a schedule, but its terminal action is still
only **stage**. Read the exact immutable contract and retention boundary in
[the evolution boundary](docs/evolution-boundary.md).

Every report uses a versioned Evidence IR envelope and keeps atomic statuses:
`PASS`, `FAIL`, `UNKNOWN`, and `NOT_APPLICABLE`. `UNKNOWN` is work left to
verify—not a discounted pass. Evidence levels distinguish a human declaration
(L0), local files (L1), executed commands (L2), local Git (L3), explicitly
retrieved remote data (L4), and human attestation (L5).

### Freshness is separate from proof success

Starting in v1.1.0, `audit`, `review`, and `trace` record a deterministic
`workspace_snapshot`: the Git HEAD and digests of tracked and untracked
working-tree state. When `aet evidence pack` is produced, AET compares the
supplied snapshots with the workspace at pack time.

- `EXACT_MATCH` means the reviewed, traced, and packed workspace match.
- `HEAD_MATCH_WORKTREE_DIFFERS` means the commit is unchanged but the working
  tree changed after at least one artifact was produced.
- `HEAD_DIFFERS` means the compared artifacts come from different commits.
- `INTENT_CHANGED`, `CONFIG_CHANGED`, and `UNTRACKED_SET_CHANGED` identify
  those specific freshness breaks instead of collapsing them into a generic
  workspace difference.
- `UNKNOWN` means a Git snapshot could not be captured or an older report did
  not contain one.

This is intentionally a separate `snapshot_binding`. A successful proof stays
`PASS` even when the workspace later becomes stale; the Viewer marks delivery
as `STALE` rather than pretending the command was never executed.

### Run Manifest: an optional delivery lifecycle

v1.2.0 adds `aet run` for cases where the relationship between independent
artifacts matters. It is a local, append-only task ledger—not an Agent runtime
or workflow engine. It never selects a command, retries work, calls a model,
or takes control of an agent host.

```text
INTENT_BOUND → AUDITED → REVIEWED → PROVEN → PACKED → CLOSED
                                      │
                         workspace or control file changes
                                      ↓
                                    STALE
```

Create one only when a delivery needs this lifecycle, then pass `--run` while
writing each normal JSON artifact. `aet run status` is read-only; `aet run
verify` records an observed stale transition and exits non-zero when stale;
`aet run close` refuses anything other than a fresh `PACKED` run.

### Context and decisions: local provenance, not Agent memory

v1.3.0 adds two optional, local JSON artifacts for a task's durable engineering
facts. They are independent of `audit`, `review`, `trace`, and `run`.

```bash
# Record discoverable instructions/Skills, then explicitly attest a read and a local reference.
aet context discover . --output .aet/context/manifest.json
aet context record --manifest .aet/context/manifest.json \
  --read AGENTS.md --reference docs/architecture.md
aet context verify --manifest .aet/context/manifest.json

# Store one source-backed project decision and verify its local sources later.
aet decision init --output .aet/decisions.json
aet decision add --ledger .aet/decisions.json --id DEC-0001 \
  --claim "Keep proof execution explicit." --evidence-state EVIDENCED \
  --source docs/productization-plan.md
aet decision list --ledger .aet/decisions.json
aet decision verify --ledger .aet/decisions.json
```

`context discover` is L1 evidence that an asset was found and hashes its
content. `context record --read` is an L5 `agent_attestation`: it records that
an agent or host claimed to read an asset; it does not prove that a model saw,
understood, or used the content. `context verify` checks asset hashes and the
captured workspace snapshot, so changed context becomes visible rather than
silently carrying a previous declaration forward.

The Decision Ledger is a small source-backed memory for maintainers, not a
generic Agent memory or RAG system. `EVIDENCED` and `INFERRED` records require
at least one local file with a SHA-256 hash; `ATTESTED` and `UNKNOWN` preserve
their weaker epistemic state. Use `aet decision supersede --id DEC-0001 --by
DEC-0002` only after the accepted replacement exists. Verification establishes
whether recorded source bytes still match—not whether a decision is eternally
correct.

## Quality and current results

AET deliberately reports a status matrix rather than a synthetic “agent trust
score.” Its only numeric model, `aet triage`, exposes its weights and is used
only to order remediation work.

| Release check | v1.5.0 result | How to reproduce |
| --- | --- | --- |
| Regression suite | 34 tests passed | `uv run --no-editable --reinstall-package agent-engineering-toolkit python -m unittest discover -s tests -v` |
| Strict self-audit | 0 `FAIL`, 0 `UNKNOWN` in the configured production Skill scope | `uv run --no-editable aet audit . --strict` |
| Intent review | Release diff must stay inside the reviewed contract | `uv run --no-editable aet review . --base v1.3.0 --intent aet.intent.json` |
| Distribution smoke | Wheel built and invoked in an isolated environment | `uv build` then install the wheel shown below |
| Delivery automation | CI on `main`, plus tag-driven GitHub Release workflow | [Actions](https://github.com/AdvancingTitans/agent-engineering-toolkit/actions) |

These checks prove the stated mechanics, not that every repository or every
agent decision is safe. See the [rule catalog](docs/rule-catalog.md) and
[security and retention boundary](docs/security-and-retention.md) for exactly
what AET does and does not claim.

## Quick start

### Install the released CLI

Install the published GitHub Release wheel with [uv](https://docs.astral.sh/uv/):

```bash
uv tool install https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/download/v1.5.0/agent_engineering_toolkit-1.5.0-py3-none-any.whl
aet --version
```

Or try the current source checkout without installing it globally:

```bash
git clone https://github.com/AdvancingTitans/agent-engineering-toolkit.git
cd agent-engineering-toolkit
uv run --no-editable aet audit . --strict
```

### Run a first safe audit

```bash
aet init --output aet.toml
aet audit . --strict --format json --output .aet/evidence/audit.json
```

`aet.toml` makes scan inclusions and exclusions reviewable. Exclusions require
a reason; `init` writes a candidate and never overwrites an existing file.

### Add AET to an agent host

Copy the entire [`skills/agent-engineering-toolkit/`](skills/agent-engineering-toolkit/)
directory into your host's Skill directory. For example, a Codex installation
can use:

```bash
cp -R skills/agent-engineering-toolkit ~/.codex/skills/
```

Hosts without a native Skill loader can give the agent this `SKILL.md` as
instructions and make the `aet` executable available on `PATH`.

## How to use AET

### 1. Audit instructions before the agent works

```bash
aet audit . --strict --format sarif --output .aet/evidence/audit.sarif
```

Audit finds broken local references and command targets, stale absolute paths,
context bloat, duplicated directives, and malformed or incomplete Skills.

### 2. Review a diff against human intent

Write a small `aet.intent.json` that declares the approved paths, change
budget, and proofs. AET ships a [minimal example](examples/aet.intent.example.json).

```bash
cp examples/aet.intent.example.json aet.intent.json
aet review . --base main --format json --output .aet/evidence/review.json
```

Review proves the contract and scope are satisfied; it intentionally does not
run the declared commands.

### 3. Bind an executed proof and make a handoff pack

```bash
aet trace --proof unit-tests --intent aet.intent.json \
  --output .aet/evidence/trace.json -- \
  python -m unittest discover -s tests -v

aet evidence pack \
  --audit .aet/evidence/audit.json \
  --review .aet/evidence/review.json \
  --trace .aet/evidence/trace.json \
  --output .aet/evidence/evidence-pack.json

aet evidence viewer --pack .aet/evidence/evidence-pack.json \
  --output .aet/evidence/evidence-viewer.html
```

Trace is opt-in, requires `--`, records only the explicit command, and stores
redacted excerpts plus hashes. The static viewer needs no server or external
assets.

### Capture a declared pytest report

`trace` never guesses which files a command wrote. When a test report matters
to the delivery claim, declare the workspace-relative path explicitly. AET
captures the completed UTF-8 text report only after the command exits, redacts
it before persistence, and embeds it in the portable Evidence Pack.

```bash
aet trace --artifact reports/junit.xml --output .aet/evidence/pytest-trace.json -- \
  pytest --junitxml=reports/junit.xml
aet evidence pack --trace .aet/evidence/pytest-trace.json \
  --output .aet/evidence/evidence-pack.json
```

Absolute, outside-workspace, missing, non-regular, undecodable, or
unredactable artifacts are `UNKNOWN`; if one was explicitly requested, Trace
returns non-zero even when pytest itself exited zero. This preserves the two
facts separately: the command ran, but its requested report was not safely
captured. A bound proof with that artifact gap remains `UNKNOWN` and cannot
advance a Run to `PROVEN`. Stdout and stderr remain excerpt-and-digest only; full report content
enters a pack solely through this explicit opt-in.

### 4. Optionally record a delivery lifecycle

```bash
aet run init --intent aet.intent.json --output .aet/runs/release.json
aet audit . --format json --output .aet/evidence/audit.json --run .aet/runs/release.json
aet review . --base main --format json --output .aet/evidence/review.json --run .aet/runs/release.json
aet trace --proof unit-tests --intent aet.intent.json --output .aet/evidence/trace.json \
  --run .aet/runs/release.json -- python -m unittest discover -s tests -v
aet evidence pack --audit .aet/evidence/audit.json --review .aet/evidence/review.json \
  --trace .aet/evidence/trace.json --output .aet/evidence/evidence-pack.json \
  --run .aet/runs/release.json
aet run verify --run .aet/runs/release.json
aet run close --run .aet/runs/release.json
```

Keep `.aet/` ignored when using a Run; otherwise generated evidence is itself
an untracked workspace change and is correctly reported as stale.

## Repo Archaeologist

`aet evolve` is for the question a changelog cannot answer alone: **what
changed, when, what source links it, and what is still unknown?**

```bash
aet evolve plan . --question "Why was this release made?" --output .aet/evolve/plan.json
aet evolve collect . --question "Why was this release made?" --output .aet/evolve/run
aet evolve build --manifest .aet/evolve/run/source-manifest.json --output .aet/evolve/run
aet evolve report --graph .aet/evolve/run/object-graph.json --output .aet/evolve/run
```

The default flow is local and offline: Git objects and repository documents.
When requested, `--remote github` adds explicitly retrieved Issues, pull
requests, and releases to the source manifest. A tag-to-commit relation may be
`DIRECT`; a textual `#123` mention without its target stays a `CANDIDATE`.
AET never turns that distinction into a story about private author intent.

Read the full [`evolve` contract](docs/evolve-contract.md).

## Why it is different

- **Evidence-first, not verdict-first.** Every finding keeps its location,
  remediation, source, and status; a missing check remains visible.
- **Local by default.** Static audit, review, triage, and local archaeology
  need no API key, LLM, or background service.
- **Explicit side effects.** Only Trace executes a generic command; remote
  GitHub collection is opt-in.
- **Useful across agent hosts.** The Skill guides an agent; canonical JSON,
  SARIF, and Markdown reports guide people, CI, and other tools.
- **History with epistemic boundaries.** Repo Archaeologist links evidence and
  exposes unanswered questions rather than guessing why someone made a change.

## Best fit

AET is especially useful for:

- engineers who let Codex, Claude Code, Cursor, Copilot, or similar agents
  modify repositories;
- maintainers who need a lightweight, reviewable release or handoff record;
- teams with long-lived `AGENTS.md`, `CLAUDE.md`, or reusable Skill libraries;
- developers onboarding to an unfamiliar repository and needing cited history.

It is not an agent runtime, an automatic prompt rewriter, a hosted security
platform, or a replacement for semantic tests and human review.

## Repository map

```text
src/aet/                         Deterministic CLI and evidence model
skills/agent-engineering-toolkit/ Portable cross-agent Skill and contracts
schemas/                         Versioned Evidence IR schema
tests/                           Regression tests and positive/negative fixtures
docs/                            Contracts, product rationale, security, Chinese README
examples/                        Copyable intent and workflow examples
.github/workflows/               CI and tag-driven GitHub Release automation
```

The core implementation is deliberately small: `discovery.py` finds context
assets, `rules.py` produces evidence-backed audit findings, `review.py`
compares intent to a Git diff, `evidence.py` records Trace and packs, `run.py`
records optional lifecycle transitions, `context.py` records local context
provenance, `decision.py` records source-backed project decisions,
`evolve.py` builds the repository-evolution graph, and `reporters.py` writes
portable output.

## Documentation

| Topic | Start here |
| --- | --- |
| Chinese documentation | [docs/README.zh-CN.md](docs/README.zh-CN.md) |
| Rules and gate effects | [docs/rule-catalog.md](docs/rule-catalog.md) |
| Repo Archaeologist contract | [docs/evolve-contract.md](docs/evolve-contract.md) |
| Security, privacy, and retention | [docs/security-and-retention.md](docs/security-and-retention.md) |
| Product decisions and rationale | [docs/productization-plan.md](docs/productization-plan.md) |
| Version history | [CHANGELOG.md](CHANGELOG.md) |
| Contribution guide | [CONTRIBUTING.md](CONTRIBUTING.md) |

## Contributing

The most valuable contribution is a reproducible failure, a missing boundary,
or a real workflow that AET cannot yet represent. Please read
[CONTRIBUTING.md](CONTRIBUTING.md), use the Issue forms, and keep pull requests
small enough to review against an intent contract. We welcome first-time
contributors and real-world adoption examples.

## License

MIT. See [LICENSE](LICENSE).
