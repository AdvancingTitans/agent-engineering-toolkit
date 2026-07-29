# Claude Code

Claude Code can invoke the same local `aet` CLI and consume the same JSON
contracts. Install the matching Skill folder when the host supports portable
Agent Skills, or load its `SKILL.md` as project instructions.

The shared boundary is the CLI and evidence files, not a vendor API. Command
execution requires an explicit `/aet-proof` request. A Bundle remains readable
without installing AET.

Compatibility claims are limited to the documented file and CLI contracts;
host-specific UI behavior must be smoke-tested against the actual host version.
