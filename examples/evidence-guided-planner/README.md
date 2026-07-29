# Evidence-Guided Planner examples

Build three deterministic scenarios:

```bash
uv run --no-editable python examples/evidence-guided-planner/build_example.py \
  --output /tmp/aet-planner-example
```

The output contains:

- `single-file`: an existing reproduced empty-result Finding localized to one
  adapter and its focused regression;
- `cross-module`: an AET self-review Bundle localized across Graph Builder,
  a fixed Perspective, recursive Viewer behavior, Bundle Schema
  compatibility, and focused tests;
- `needs-evidence`: a repository-wide permission request that remains
  `NEEDS_EVIDENCE` because the supplied Bundle covers only one sample adapter.

Each scenario preserves the frozen Host Candidate, Planning Context, validated
Plan package, minimal exported Skill, external diff, and verification handoff.
The build does not implement any Plan or execute its pending verification
commands. The existing improvement fixture creates its already-declared Quick
Proof while compiling the input Bundle.

## Use the cross-module Plan with a code Agent

The `cross-module/plan` directory is the exact read-only package used in the
v1.17 real-case comparison. Give the package—not edit authority—to a Host
Planner:

```text
Developer request
  → cross-module/planning-context.json
  → Host candidate
  → cross-module/plan/plan.json + references/
  → code Agent Planner reads the required edits and linkages
  → human approves any implementation outside AET
  → external diff becomes a verification handoff
```

The Plan names four required production paths, their source locators, linked
change sites, focused tests, evidence references, and preserved unknowns. It
does not claim that unexecuted tests passed.

The corresponding source-only, v1.16 evidence-only, and v1.17 Plan
observations are in
[`../../eval/evidence-guided-planner/real-case/observations.json`](../../eval/evidence-guided-planner/real-case/observations.json).
Re-score them with:

```bash
uv run --no-editable python eval/evidence-guided-planner/run_real_case.py \
  --output /tmp/aet-planner-real.json >/dev/null
cmp /tmp/aet-planner-real.json \
  eval/evidence-guided-planner/results/v1.17.0-real-codex.json
```
