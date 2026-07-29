# Evidence-Guided Planner architecture decision

Status: Accepted for implementation
Date: 2026-07-29

## Decision

The Evidence-Guided Planner is a read-only recommendation layer over the
existing Portable Evidence Bundle, Evidence Atlas, Improvement constraints,
current source tree, Proof, and Freshness surfaces.

The stable boundary is:

```text
AET Planning Context
  → Host Planner produces a strict Plan Candidate
  → AET deterministic validation
  → PROPOSED Evidence-Linked Plan
  → human review
  → external implementation
  → explicit Proof, Freshness, and Regression Lineage validation
```

AET does not provide a model client, model credentials, a general Agent loop,
an edit executor, automatic command execution, or commit/push/merge/release
operations for Planning. A Plan never writes back into Bundle Core Evidence
and never changes Evidence strength, status, conflict, counter-evidence, or
Freshness.

`/aet-plan` is an independent evidence-guided planning Skill. It is not a fifth
Quick audit Skill. Product documentation should describe the surface as
“Four Quick Skills + Evidence-Guided Planner.”

## Repository path mapping

The delivery package's logical paths map to this repository as follows.

| Delivery-package surface | Repository path used here | Reason |
| --- | --- | --- |
| Planning core | `src/aet/planning/` | The package already uses `src/aet/` and domain subpackages. |
| CLI plan module | `src/aet/cli.py` | CLI registration and dispatch are intentionally centralized in the existing single module. Core rules remain in `src/aet/planning/`. |
| MCP Planning tools | `src/aet/mcp_server.py` | The dependency-free MCP registry and dispatcher are centralized here. Planning handlers delegate to the core. |
| Python SDK | `src/aet_bundle/__init__.py` | This is the existing optional Bundle/Atlas consumer SDK. Planning load/query helpers extend the same portable-consumer surface. |
| TypeScript SDK | `packages/evidence-bundle/runtime/planning.js`, `packages/evidence-bundle/src/index.d.ts`, and package exports | The existing `@aet/evidence-bundle` package already includes Bundle and Atlas consumer APIs, so a separate package would duplicate the portable consumer boundary. |
| Planning Schemas | `schemas/planning/*.schema.json` | Existing protocol Schemas are rooted under `schemas/`; `pyproject.toml` packages each protocol directory explicitly. |
| Host Skill | `skills/aet-plan/` | Existing portable host Skills are independent folders under `skills/`. |
| Planner documentation | `docs/evidence-guided-planner.md`, `docs/planner-helper-scenarios.md`, `docs/schemas/planning.md` | Matches the repository's product, scenario, and protocol documentation conventions. |
| Architecture source | `docs/assets/evidence-guided-planner-architecture.mmd` | Existing editable architecture sources are stored under `docs/assets/`. |
| Examples | `examples/evidence-guided-planner/` | Existing end-to-end examples live under `examples/`. |
| Unit and integration tests | `tests/planning/` and `tests/integration/` | `unittest discover -s tests` is the canonical gate and discovers both layouts. |
| Localization fixtures | `tests/fixtures/planning/` | Existing frozen protocol and product fixtures live under `tests/fixtures/`. |

No parallel Bundle schema, Atlas graph, Change Scope authority, Proof format, or
Freshness model will be introduced.

## Existing interfaces to reuse

| Need | Existing interface |
| --- | --- |
| Strict Bundle loading and validation | `aet.bundle.validate_bundle`, backed by `aet.bundle.load_bundle` |
| Duplicate-key and safe-path Bundle parsing | `aet.bundle.loader._decode_json` semantics and Bundle loader containment rules |
| Bundle identity | `manifest.bundle.id` and `manifest.bundle.content_hash` from the validated Bundle |
| Bundle policy | `policy.workspace_policy`, `policy.command_policy`, and `policy.budgets` |
| Atlas load and identity validation | `aet.atlas.load_evidence_atlas` and `aet.atlas.validate_evidence_atlas` |
| Atlas bounded navigation | `get_node_subgraph`, `trace_claim_support`, `trace_conflict`, `trace_freshness_impact`, and `explain_node` |
| Improvement scope | `ImprovementConstraint.allowed_paths`, `protected_paths`, and `verification_requirements` |
| Default protected patterns | `aet.improvement.constraint.rules.PROTECTED_PATHS` |
| Current Git/worktree binding | `aet.evidence.workspace_snapshot` |
| Canonical JSON style | Sorted keys, UTF-8, `allow_nan=False`, and stable newline termination used by Bundle/Atlas/Improvement writers |
| CLI registration | `aet.cli.build_parser` and `aet.cli.main` |
| MCP registry and dispatch | `aet.mcp_server._TOOLS` and `aet.mcp_server.call_tool` |
| Python portable consumer API | `src/aet_bundle/__init__.py` |
| TypeScript strict JSON and portable API | `packages/evidence-bundle/runtime/strict-json.js` and `packages/evidence-bundle/runtime/index.js` |
| Proof and Freshness | Existing Quick Proof receipt and Freshness validators; Planning only emits a later verification request |
| Regression Lineage | Existing Evidence Atlas `regression-lineage` Perspective; Planning records unresolved handoff links without manufacturing graph evidence |

## Source authority and fail-closed rules

Atlas paths and symbols are navigation seeds. Before a `REQUIRED` edit can be
accepted, the current workspace file is read again, contained under the
workspace after symlink resolution, hashed, and matched to the proposed path
and source reference. Missing or stale sites do not become current facts.

An absent Atlas may degrade to validated Bundle plus current Source. An absent
Bundle may produce a Source-only Context, but its Plan cannot exceed
`NEEDS_EVIDENCE`. Bundle/Atlas identity mismatch, path escape, protected paths,
forged references, execution/write claims, and unresolved critical conflicts
fail closed.

The Plan authority is always `PROPOSED`. `READY_FOR_HUMAN_REVIEW` means only
that the bounded plan passed deterministic structural and reference checks; it
does not mean the plan is correct, implemented, tested, or verified.

## Harness Handbook reference boundary

The design uses the following ideas from
`Ruhan-Wang/Harness_Handbook` as product reference:

- navigate through a compact derived index before reading source;
- treat real source as the ground truth for the proposed location;
- keep the Planner plan-only and read-only;
- resynchronize derived navigation after a real external change.

The implementation does not copy Harness Handbook code, prompts, generated
handbook formats, model clients, NexAU integration, tree-sitter dependency,
OpenAI-compatible endpoint handling, or exact-text edit executor protocol.
AET's Atlas remains a source-backed evidence projection rather than a complete
code handbook, and AET never adopts the Handbook's “every edit site” claim as
an authority statement. Planning coverage remains bounded and explicitly
`BEST_EFFORT`, `PARTIAL`, or `UNKNOWN` unless all
`BOUNDED_COMPLETE` preconditions are deterministically satisfied.

Reference reviewed on 2026-07-29:
<https://github.com/Ruhan-Wang/Harness_Handbook>
