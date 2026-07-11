---
name: agent-engineering-toolkit
description: Audit a repository's coding-agent context and Skills with the local aet CLI. Use before agent implementation, before installing or publishing a Skill, when AGENTS.md/CLAUDE.md/SKILL.md references may have drifted, or when a PR needs machine-readable context-health evidence.
---

# Agent Engineering Toolkit

Current Skill version: `0.2.0` (v0.2 release)

Use the repository-local `aet` CLI to make deterministic, read-only findings
about agent instructions and Skills. Never claim a remote service, dynamic
command, or semantic workflow is valid unless another tool has actually proved
it.

## Workflow

1. From the repository root, run `uv run aet audit .`.
2. Read every `FAIL` first. Its file and line are the primary evidence; fix the
   target or the reference rather than suppressing the finding.
3. Treat `UNKNOWN` as an explicit verification gap. It is not a pass.
4. For CI or a handoff, emit a stable artifact:

   ```bash
   uv run aet audit . --format json --output .aet/evidence/audit.json --strict
   ```

5. Before saying the context is ready, rerun the same command and report its
   summary. A non-zero exit status means it is not ready under that gate.

## Intent Gate

For a change review, require a human-authored `aet.intent.json`, then run:

```bash
uv run aet review --base main
```

Read every `FAIL` first. `review` verifies changed-path scope and budget plus
the presence of local proof evidence. It deliberately does not execute proof
commands; run those separately before claiming the proof passed.

## Boundaries

v0.2 audits local paths, context shape, Skill structure, and a Git diff against
a human-authored intent contract. It does not run referenced or proof commands,
contact MCP servers, or judge model output. Preserve those limits in every
user-facing conclusion.

For format and rule details, read [the v0.1 contract](references/v0.1-contract.md)
and [the v0.2 contract](references/v0.2-contract.md).

Delete this entire "Structuring This Skill" section when done - it's just guidance.]

## [TODO: Replace with the first main section based on chosen structure]

[TODO: Add content here. See examples in existing skills:
- Code samples for technical skills
- Decision trees for complex workflows
- Concrete examples with realistic user requests
- References to scripts/templates/references as needed]

## Resources (optional)

Create only the resource directories this skill actually needs. Delete this section if no resources are required.

### scripts/
Executable code (Python/Bash/etc.) that can be run directly to perform specific operations.

**Examples from other skills:**
- PDF skill: `fill_fillable_fields.py`, `extract_form_field_info.py` - utilities for PDF manipulation
- DOCX skill: `document.py`, `utilities.py` - Python modules for document processing

**Appropriate for:** Python scripts, shell scripts, or any executable code that performs automation, data processing, or specific operations.

**Note:** Scripts may be executed without loading into context, but can still be read by Codex for patching or environment adjustments.

### references/
Documentation and reference material intended to be loaded into context to inform Codex's process and thinking.

**Examples from other skills:**
- Product management: `communication.md`, `context_building.md` - detailed workflow guides
- BigQuery: API reference documentation and query examples
- Finance: Schema documentation, company policies

**Appropriate for:** In-depth documentation, API references, database schemas, comprehensive guides, or any detailed information that Codex should reference while working.

### assets/
Files not intended to be loaded into context, but rather used within the output Codex produces.

**Examples from other skills:**
- Brand styling: PowerPoint template files (.pptx), logo files
- Frontend builder: HTML/React boilerplate project directories
- Typography: Font files (.ttf, .woff2)

**Appropriate for:** Templates, boilerplate code, document templates, images, icons, fonts, or any files meant to be copied or used in the final output.

---

**Not every skill requires all three types of resources.**
