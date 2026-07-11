# Cross-agent use

The canonical portable artifact is this complete Skill folder: `SKILL.md`, its
`references/`, and optional `agents/` metadata. The runtime boundary is the
`aet` CLI and its JSON/SARIF files, not the host agent's internal trace format.

## Host contract

Any agent can use this Skill if it can read these instructions and invoke a
local command. A native Skill host should install the complete folder. A host
without native Skills should include `SKILL.md` in its project instructions and
make `aet` available on `PATH`.

Use explicit paths and preserve command exit codes. Attach generated JSON or
SARIF to the handoff. Never replace an `UNKNOWN` with an assertion merely
because another agent uses different terminology or a different tool runtime.

## Compatibility boundaries

- Do not depend on Codex-, Claude-, Cursor-, or Copilot-specific APIs.
- Do not require an MCP server, model provider, or network access for audit or
  review.
- Treat `agents/openai.yaml` as optional UI metadata. It is not part of the
  portable workflow.
- If `aet` is unavailable, report the blocked verification rather than trying
  to imitate its findings in prose.
