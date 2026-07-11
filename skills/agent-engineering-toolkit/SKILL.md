---
name: agent-engineering-toolkit
description: Produce evidence-backed audits and intent-to-diff reviews for coding-agent work with the aet CLI. Use before an agent changes a repository, before merging an agent-authored diff, when AGENTS.md/CLAUDE.md/SKILL.md may have drifted, or when a handoff needs portable JSON or SARIF evidence. Works with any agent that can read instructions and run a local CLI.
---

# Agent Engineering Toolkit

Current Skill version: `1.3.0` (Evidence Plane: audit, review, trace, evidence, evolve, optional Run Manifest, Context Manifest, and Decision Ledger)

Use the `aet` CLI as the source of truth. The host agent may choose its own
shell or package runner, but must preserve the commands' exit status and attach
the emitted evidence instead of paraphrasing it as unverified fact.

## Route the request

Choose one initial surface. If the request is ambiguous, default to read-only `audit` or `evolve plan`.

| User need | Initial command | Output |
| --- | --- | --- |
| Trust current instructions / Skills | `aet audit . --strict` | Audit report |
| Check a proposed or completed diff | `aet review . --base <base>` | Review report |
| Prove a command actually ran | `aet trace --proof <id> … -- <argv>` | Trace + pack |
| Understand why a repo changed | `aet evolve plan/collect/build/report` | Evolution Pack |
| Record which local context was available | `aet context discover/record/verify` | Context Manifest |
| Preserve a source-backed project decision | `aet decision init/add/verify` | Decision Ledger |

Repo Archaeologist example: “Explain why this repository adopted a plugin architecture; link releases, PRs, Issues, commits, and README changes, and separate direct evidence from candidates.” Use `aet evolve`; never invent author intent.

## Workflow

1. Ensure `aet` is available on `PATH`, or run it from a project checkout with
   its documented package runner.
2. Before implementation, run:

   ```bash
   aet audit . --format json --output .aet/evidence/audit.json --strict
   ```

3. Read every `FAIL` first. Treat `UNKNOWN` as a verification gap, never as a
   pass. Correct the repository or the reference, then rerun the same command.
4. Before delivery, require a human-reviewed `aet.intent.json` and run:

   ```bash
   aet review . --base main --format json --output .aet/evidence/review.json
   ```

5. When command execution is explicitly requested, run it only through Trace,
   then compile the available reports into a portable pack:

   ```bash
   aet trace --proof <proof-id> --intent aet.intent.json --output .aet/evidence/trace.json -- <command> [args...]
   aet evidence pack \
     --audit .aet/evidence/audit.json \
     --review .aet/evidence/review.json \
     --trace .aet/evidence/trace.json \
     --output .aet/evidence/evidence-pack.json
   ```

   `--` is required. Trace is opt-in; neither audit nor review may execute a
   declared proof command. Attach the generated JSON to the handoff.

6. For archaeology, use:

   ```bash
   aet evolve plan . --question "<question>" --output .aet/evolve/plan.json
   aet evolve collect . --question "<question>" --output .aet/evolve/run
   aet evolve build --manifest .aet/evolve/run/source-manifest.json --output .aet/evolve/run
   aet evolve report --graph .aet/evolve/run/object-graph.json --output .aet/evolve/run
   ```

   For a delivery that needs an explicit lifecycle, initialize an optional Run
   Manifest before producing artifacts, then attach each generated JSON with
   `--run .aet/runs/<name>.json`. A Run records artifact order and marks the
   delivery `STALE` when its recorded workspace no longer matches; it never
   chooses or executes a command for the user.

   Use `--remote github` only on explicit request. Missing remote data is `UNKNOWN`; a textual `#123` relation is only a candidate until source objects establish it.

7. Report the command, exit status, summary, and evidence-file path. Do not
   claim a referenced command, remote MCP, or model output was verified unless
   another tool actually performed and recorded that check.

8. For an explicit context boundary, use:

   ```bash
   aet context discover . --output .aet/context/manifest.json
   aet context record --manifest .aet/context/manifest.json --read AGENTS.md
   aet context verify --manifest .aet/context/manifest.json
   ```

   Discovery is L1 evidence that an asset existed with a recorded hash.
   `--read` is only an L5 agent/host attestation; it cannot prove the model
   read, understood, or used the asset. Do not describe this feature as RAG,
   generic Agent memory, or host telemetry.

9. For a durable, source-backed project decision, use:

   ```bash
   aet decision init --output .aet/decisions.json
   aet decision add --ledger .aet/decisions.json --id DEC-0001 \
     --claim "Keep proof execution explicit." --evidence-state EVIDENCED \
     --source docs/productization-plan.md
   aet decision verify --ledger .aet/decisions.json
   ```

   `EVIDENCED` and `INFERRED` decisions require local hashed sources.
   Verification proves only that recorded bytes still match; it does not make
   the decision universally or permanently correct.

## Portable use

This folder is the canonical, tool-neutral Skill. Install or load the complete
folder in any host that supports `SKILL.md` folders. If the host has no native
Skill loader, place this file in that agent's project instructions and ensure
the `aet` executable is available. The optional `agents/` metadata is
OpenAI-specific UI metadata; other hosts may ignore it.

For compatibility rules and output contracts, read
[cross-agent use](references/cross-agent-use.md), then the applicable
[audit contract](references/v0.1-contract.md),
[review contract](references/v0.2-contract.md), or
[Evidence Pack and Trace contract](references/v0.3-contract.md), then the [v1 product contract](references/v1-contract.md).

## Boundaries

Audit, review, and Evidence Pack compilation are deterministic and local.
Only `aet trace` executes a command, and only the explicit argv after `--`.
Trace redacts configured secret patterns before persistence; undecodable or
unredactable fields remain `UNKNOWN`. No command, MCP server, or model output
is verified unless Trace records it.
