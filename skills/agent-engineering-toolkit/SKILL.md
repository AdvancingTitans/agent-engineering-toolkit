---
name: agent-engineering-toolkit
description: Produce evidence-backed audits and intent-to-diff reviews for coding-agent work with the aet CLI. Use before an agent changes a repository, before merging an agent-authored diff, when AGENTS.md/CLAUDE.md/SKILL.md may have drifted, or when a handoff needs portable JSON or SARIF evidence. Works with any agent that can read instructions and run a local CLI.
---

# Agent Engineering Toolkit

Current Skill version: `0.2.1` (portable Agent Skill packaging)

Use the `aet` CLI as the source of truth. The host agent may choose its own
shell or package runner, but must preserve the commands' exit status and attach
the emitted evidence instead of paraphrasing it as unverified fact.

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

5. Report the command, exit status, summary, and evidence-file path. Do not
   claim a referenced command, remote MCP, or model output was verified unless
   another tool actually performed and recorded that check.

## Portable use

This folder is the canonical, tool-neutral Skill. Install or load the complete
folder in any host that supports `SKILL.md` folders. If the host has no native
Skill loader, place this file in that agent's project instructions and ensure
the `aet` executable is available. The optional `agents/` metadata is
OpenAI-specific UI metadata; other hosts may ignore it.

For compatibility rules and output contracts, read
[cross-agent use](references/cross-agent-use.md), then the applicable
[audit contract](references/v0.1-contract.md) or
[review contract](references/v0.2-contract.md).

## Boundaries

v0.2 is deterministic and local. It does not execute referenced or proof
commands, contact MCP servers, judge model output, or infer intent from prose.
Evidence Pack and opt-in command Trace are planned for v0.3; do not claim they
exist until their CLI commands and schema have shipped.
