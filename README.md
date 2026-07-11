# Agent Engineering Toolkit

**Evidence-first guardrails for coding agents.** AET makes four things reviewable: the instructions an agent reads, the scope it is allowed to change, the commands that actually ran, and the evidence behind a repository's history.

It is local-first, deterministic by default, has no API-key or LLM dependency, and never turns `UNKNOWN` into a pass by averaging it into a score.

## Install

```bash
uv tool install agent-engineering-toolkit
aet --version
```

For a checkout: `uv run --no-editable aet audit . --strict`.

## Four product surfaces

| Need | Command | Evidence produced |
| --- | --- | --- |
| Trust current instructions / Skills | `aet audit .` | Audit JSON / Markdown / SARIF |
| Check a proposed or completed diff | `aet review . --base main` | Intent-gate review |
| Prove a command actually ran | `aet trace --proof … -- …` | Redacted Trace + Evidence Pack |
| Why did this repository evolve this way? | `aet evolve …` | Evolution Pack / timeline / cited report |

### Audit context and Skills

```bash
aet init --output aet.toml
aet audit . --strict --format json --output .aet/evidence/audit.json
```

`aet.toml` keeps scan boundaries and exclusions explicit and reviewable. `init` writes a candidate only and never overwrites it. AET detects broken relative references, stale absolute local paths, command targets, context bloat, duplicate directives, and Skill integrity.

### Review a change against human intent

Create a concise `aet.intent.json`, then run:

```bash
aet review . --base main --format json --output .aet/evidence/review.json
```

The gate checks contract validity, changed-path budget, allowed paths, and declared local proof evidence. It does not execute proof commands.

### Bind real execution to a proof

```bash
aet trace --proof unit-tests --intent aet.intent.json --output .aet/evidence/trace.json -- \
  uv run --no-editable python -m unittest discover -s tests -v
aet evidence pack --audit .aet/evidence/audit.json --review .aet/evidence/review.json \
  --trace .aet/evidence/trace.json --output .aet/evidence/evidence-pack.json
aet evidence viewer --pack .aet/evidence/evidence-pack.json --output .aet/evidence/evidence-viewer.html
```

Trace is opt-in and requires `--`. It stores redacted argv/log excerpts, exit status, timestamps, Git identity, and content digests. A supplied `--proof` binds Trace to the intent hash; a mismatch is `FAIL`, a missing trace is `UNKNOWN`.

### Repo Archaeologist: `aet evolve`

`evolve` is a first-class AET use case, not a separate product. It links Git objects and documentation without claiming to know an author's private intent.

```bash
aet evolve plan . --question "Why was this release made?" --output .aet/evolve/plan.json
aet evolve collect . --question "Why was this release made?" --output .aet/evolve/run
aet evolve build --manifest .aet/evolve/run/source-manifest.json --output .aet/evolve/run
aet evolve report --graph .aet/evolve/run/object-graph.json --output .aet/evolve/run
```

The output contains `source-manifest.json`, `object-graph.json`, `linkage-report.json`, `evolution-pack.json`, `timeline.mmd`, `decision-index.json`, `unanswered-questions.md`, and `evolution-report.md`. Tag/commit and document/version relations are `DIRECT`; unresolved textual `#123` mentions are only `CANDIDATE`.

Local Git/docs are offline defaults. Use a GitHub export with `--source-export`; live retrieval requires explicit `--remote github` and records request status/source hashes. Missing remote data is `UNKNOWN`, never guessed.

## Evidence model and triage

Reports use a versioned Evidence IR envelope (`schema_version`, `run_id`, `tool`, `scope`, `sources`, `claims`, and a status summary). Levels are L0 declared intent, L1 static local file, L2 executed Trace, L3 Git history, L4 explicitly retrieved remote data, and L5 human attestation.

`aet triage --report audit.json --output triage.json` provides an explainable repair-order score. It exposes its factors/model version and **never changes** `PASS`/`FAIL`/`UNKNOWN` or release policy.

## Agent Skill

The portable Skill is [`skills/agent-engineering-toolkit/`](skills/agent-engineering-toolkit/). It routes agents to audit, review, evidence, or evolve with the smallest safe workflow. Read its [v1 contract](skills/agent-engineering-toolkit/references/v1-contract.md).

## Development and release verification

```bash
uv run --no-editable --reinstall-package agent-engineering-toolkit python -m unittest discover -s tests -v
uv run --no-editable aet audit . --strict --format json --output .aet/evidence/audit.json
uv build
uv run --isolated --with dist/agent_engineering_toolkit-1.0.0-py3-none-any.whl aet --version
```

GitHub Actions runs the suite, strict self-audit, build, and isolated wheel smoke on pushes/PRs. A `v*` tag creates a GitHub Release with build artifacts.

## Security boundary

Read [security and retention](docs/security-and-retention.md) before sharing artifacts. AET does not upload repository data; generic execution is only via opt-in Trace; remote history collection is explicit; and `.aet/` is ignored because it can contain reviewed paths and redacted excerpts.

## License

MIT. See [LICENSE](LICENSE).
