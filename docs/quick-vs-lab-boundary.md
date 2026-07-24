# AET Quick and AET Lab boundary

AET has two product layers in one repository. They share evidence and binding
protocols but do not share the default installation surface or execution path.

## AET Quick

Quick is the default product for individual developers and daily coding-Agent
work. It exposes four independent Skills:

- `/aet-check`: inspect Agent engineering assets;
- `/aet-scope`: investigate whether changes fit the task;
- `/aet-proof`: execute and bind one real validation;
- `/aet-fresh`: determine whether an earlier proof still applies.

Quick is narrow, bounded, and stop-after-report. It may use an LLM as a
constrained investigator through the host Skill, but tool facts, proof
execution, freshness, and grounding remain deterministic. It does not require
users to understand Evidence IR, Candidate IR, Gate Plans, Shadow, Stage, or
Adopt.

Default Quick installation exposes only these four Skills. The existing
canonical Skill and native CLI commands remain available for compatibility for
at least one major-version cycle, but they are not the primary first-run
vocabulary.

## AET Lab

Lab is an opt-in advanced surface for Agent engineers, Skill authors, and
platform teams. It contains:

- Evidence Only mining;
- Quality diagnosis and regression promotion;
- Candidate IR and replay;
- Gate Plans and tournaments;
- Shadow evaluation;
- Stage and explicit human adoption;
- statistical power and historical Gate analysis;
- governance-asset evolution.

Lab may take longer, use multiple model or host calls, and require isolated
evaluation fixtures. It is never started by a Quick command, never loaded by
the default Quick Skill installation, and never becomes a dependency of the
static Quick core.

## Optional extensions

Context and Decision Ledger are optional project-memory/provenance utilities.
Repository evolution and archaeology remain advanced research and maintenance
surfaces. Evidence Pack, HTML/SVG viewers, and large repository audit
showcases remain advanced outputs, compatibility surfaces, documentation
examples, or benchmark fixtures rather than default Quick artifacts.

## Shared invariants

Both layers preserve:

- Evidence IR and content-addressed provenance;
- proof and workspace-snapshot binding;
- freshness states;
- RulePack identity;
- redaction;
- deterministic findings;
- `PASS`, `FAIL`, `UNKNOWN`, and `NOT_APPLICABLE` as authoritative statuses;
- explicit human authority for mutation, publication, and adoption.

Neither layer produces a holistic trust score. LLM reasoning can investigate,
compare explanations, and form a grounded engineering judgment; it cannot
forge evidence or become the sole authority for release or adoption.

## Compatibility mapping

| Existing surface | Quick surface | Product position |
| --- | --- | --- |
| `aet audit` | `/aet-check` | advanced native compatibility |
| `aet review` | `/aet-scope` | native compatibility |
| `aet trace` | `/aet-proof` | deterministic executor |
| evidence receipt/freshness | `/aet-fresh` | deterministic freshness engine |
| Evidence Pack | none by default | advanced |
| Context / Decision | none by default | optional extension |
| Evolve / Quality / Learn | none by default | Lab |

Existing Evidence IR and receipts are not discarded. Quick adapters must
consume compatible existing proof material where the required bindings exist;
missing new bindings remain `UNKNOWN`.
