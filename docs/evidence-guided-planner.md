# Evidence-Guided Planner

The Evidence-Guided Planner is a deterministic, read-only bridge between AET
evidence and a Host Planner such as Codex or Claude Code:

1. AET builds a bounded `planning-context/1.0` document.
2. The Host Planner returns strict `plan-candidate/1.0` JSON.
3. AET validates every path and reference, then writes a portable Plan package
   whose authority remains `PROPOSED`.

AET does not embed a model client, edit workspace source, execute verification
commands, or promote observations into evidence.

## Build a Planning Context

```bash
aet plan context \
  --workspace . \
  --request-text "Update the parser and its focused tests." \
  --bundle path/to/bundle \
  --allowed-path src/parser.py \
  --allowed-path tests/test_parser.py \
  --verification "uv run pytest tests/test_parser.py" \
  --output context.json
```

`--atlas` is optional. When supplied, its Bundle identity must match the
validated Bundle. Without a Bundle, the context is source-only and records an
evidence gap instead of inventing evidence.

## Validate a Host Candidate

```bash
aet plan validate-candidate \
  --context context.json \
  --candidate candidate.json \
  --output .aet/plans/PLAN-001
```

The candidate must be strict JSON. Markdown fences, duplicate keys, unknown
fields, unresolved references, protected paths, path escapes, identity
mismatches, and dependency cycles fail closed.

## Inspect a Plan Package

```bash
aet plan validate .aet/plans/PLAN-001
aet plan show .aet/plans/PLAN-001
aet plan explain .aet/plans/PLAN-001 --edit EDIT-001
aet plan trace .aet/plans/PLAN-001 --reference REF-001
aet plan gaps .aet/plans/PLAN-001
```

These Helper commands only read the validated package. They do not add facts or
change the original Plan.

Export a self-contained single-Plan Skill:

```bash
aet plan export-skill .aet/plans/PLAN-001 \
  --target codex \
  --output .aet/skills/aet-plan-PLAN-001
```

Supported targets are `codex`, `claude-code`, and `generic`. The exporter copies
only the Plan and references used by its Edit Items, rejects secret-like
material, and seals the result with SHA-256.

After an external Agent implements a reviewed Plan, create a pending
verification handoff:

```bash
git diff --binary > agent.diff
aet plan verification-handoff .aet/plans/PLAN-001 \
  --diff agent.diff \
  --output verification-request.json
```

This parses the diff as data. It reports planned, changed, and unplanned paths;
maps touched Edit Items and tests; records stale references and unresolved
Regression Lineage; and emits Proof candidates with status `UNKNOWN` and
execution status `PENDING`. It never runs their argv.

## Portable Package

A complete package contains canonical request, context summary, validated Plan,
Markdown rendering, references, diagnostics, consumer guidance, a minimal
single-Plan Skill, and a manifest binding every file by SHA-256. Validation
rejects missing, extra, modified, or symlinked package files, so a copied
package remains independently consumable.

## Status and coverage

Plan status is one of:

- `READY_FOR_HUMAN_REVIEW`: the bounded Candidate passed validation;
- `NEEDS_EVIDENCE`: critical evidence, source, scope, or verification is
  missing;
- `PARTIAL`: an explicit budget omitted context;
- `BLOCKED`: identity, reference, protected-path, path, or Candidate integrity
  failed closed;
- `SUPERSEDED`: a later identity invalidated this Plan.

Coverage is separate from status. `BOUNDED_COMPLETE` is rejected when the
Context contains omitted data, unsupported source, critical gaps, unresolved
high-priority conflicts, missing references, or unresolved scope. The normal
claim is `BEST_EFFORT`; AET does not guarantee finding every modification point.

## Host Skill

The repository Skill is [`skills/aet-plan`](../skills/aet-plan/SKILL.md). Its
instruction layers are deliberately separate:

1. Skill safety and authority rules;
2. deterministic Planning policy and protected paths;
3. the user request within that policy;
4. Planning Context, Bundle, Atlas, Issue text, and source as untrusted data;
5. Candidate output, which has no authority until validated.

Instructions embedded in source comments, Bundle prose, Issues, or Candidate
fields cannot grant permission or change scope.

## MCP

The existing stdio server exposes eight Planning tools:

```text
aet_plan_build_context
aet_plan_validate_candidate
aet_plan_get
aet_plan_explain_edit
aet_plan_trace_reference
aet_plan_list_gaps
aet_plan_export_skill
aet_plan_build_verification_handoff
```

Planning MCP paths must stay inside the declared workspace. Context and
Candidate validation return structured data instead of writing packages.
Skill export returns a bounded in-memory file map. All results carry a Schema
version and omission counts; no tool reads environment secrets or executes
commands.

## Python SDK

The optional `aet_bundle` convenience package reuses the same validators:

```python
from aet_bundle import (
    build_verification_handoff,
    explain_edit,
    load_plan,
    query_plan_edits,
    render_planner_context,
    validate_plan,
)

plan = load_plan(".aet/plans/PLAN-001")
required = query_plan_edits(plan, "src/aet/parser.py")
explanation = explain_edit(plan, required[0]["edit_id"])
report = validate_plan(".aet/plans/PLAN-001")
handoff = build_verification_handoff(
    ".aet/plans/PLAN-001",
    "diff --git a/src/aet/parser.py b/src/aet/parser.py\n",
)
```

`render_planner_context` fails on a character-budget overflow instead of
silently truncating.

## TypeScript SDK

The existing `@aet/evidence-bundle` package is the repository's portable
artifact SDK, so it also exports:

```ts
import {
  loadPlan,
  queryPlanEdits,
  validatePlanReferences,
} from "@aet/evidence-bundle";

const plan = await loadPlan(".aet/plans/PLAN-001");
const edits = queryPlanEdits(plan, { disposition: "REQUIRED" });
const report = validatePlanReferences(plan, references);
```

The loader verifies the Plan Manifest, exact file set, SHA-256 hashes,
identities, and reference closure before returning the Plan.

## Development and evaluation

Run the three end-to-end examples:

```bash
uv run --no-editable python examples/evidence-guided-planner/build_example.py \
  --output /tmp/aet-planner-example
```

Run the frozen 20-case comparison:

```bash
python3 eval/evidence-guided-planner/run_benchmark.py
```

The benchmark compares frozen `source_only`, `bundle`, and `planner_protocol`
predictions. It does not invoke a Planner during scoring and does not treat
Token count or elapsed time as the sole success criterion.

### Real code-Agent case

The real-case evaluation asks Codex `gpt-5.6-sol` to localize an AET change
across Graph Builder, one fixed Perspective, recursive Viewer behavior, Bundle
compatibility, and focused tests. It records three distinct planning inputs:

| Group | Input available to the Planner |
| --- | --- |
| `source_only` | Current source only, under fixed source-root and generated/vendor exclusions |
| `v1_16_evidence_only` | Current source + validated Bundle + matching Atlas |
| `v1_17_plan` | The validated Plan package produced from Planning Context and Host Candidate |

```bash
uv run --no-editable python eval/evidence-guided-planner/run_real_case.py \
  --output /tmp/aet-planner-real.json >/dev/null
cmp /tmp/aet-planner-real.json \
  eval/evidence-guided-planner/results/v1.17.0-real-codex.json
```

The checked-in [Gold](../eval/evidence-guided-planner/real-case/gold.json),
[structured observations](../eval/evidence-guided-planner/real-case/observations.json),
and [result](../eval/evidence-guided-planner/results/v1.17.0-real-codex.json)
are separate artifacts. The scorer reports required-path recall, production
decision precision, disposition accuracy, test recall, evidence-reference
coverage, source-location coverage, edit-linkage coverage, and `UNKNOWN`
preservation independently.

For this one-run-per-group observation, v1.17 reached 100% on all eight named
metrics. Source-only also reached 100% required-path and test recall, so those
two metrics did not improve; its production decision precision was 44.44%
because it proposed five unrelated production paths. v1.16 evidence-only
reached 100% path precision, references, source locations, and linkages, but
missed focused tests and half of the required dispositions and unknowns.

The result is a bounded case observation, not a holistic trust score or a
general model-quality claim. An initial source-only attempt that traversed
vendored/minified assets was rejected as a harness failure, then rerun under
the same controlled source boundary as the other groups.

## Relationship to v1.16

v1.16 introduced two relevant upstream artifacts:

- Evidence Atlas: a canonical Graph and fixed Perspectives derived from a
  validated Bundle;
- Improvement Analyzer: a human report and bounded `PROPOSED` Agent task
  derived from the same evidence IDs.

v1.17 adds a downstream planning bridge. It compiles Bundle, optional matching
Atlas, current Source, human scope, protected paths, and budgets into Planning
Context; validates a Host Candidate; packages a read-only Plan; and describes
post-diff verification work. Atlas, Improvement, and Plan are siblings. None
writes advice into Bundle Core Evidence, grants edit authority, or changes
Proof from `UNKNOWN`/`PENDING` without explicit execution.

## Design boundary

The implementation borrows only the navigation-first, real-source,
read-only-planning, and post-change resynchronization ideas described by
Harness Handbook. It copies no Handbook code, exposes no Handbook-specific
protocol names, and has no runtime dependency on that repository. AET's Bundle,
Atlas, Improvement, Proof, Freshness, and Regression Lineage remain the
authority model.
