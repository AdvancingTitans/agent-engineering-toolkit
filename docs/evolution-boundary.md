# Evidence-driven Quality and Evolution boundary

AET is a local Agent engineering quality and control layer. It connects five
separate responsibilities without turning them into one autonomous loop:

```text
external Agent execution → structured evidence → deterministic quality checks
→ bounded candidate learning/evolution → explicit human adoption
```

The Agent runtime remains external. AET records narrow engineering facts,
diagnoses only through an explicit local mapping, evaluates bounded candidates,
and can stage review material. It does not automatically change a production
asset, commit, push, publish a release, create a ticket, or operate an online
quality dashboard.

## Evidence and privacy boundary

`audit`, `review`, `trace`, `context`, `decision`, `run`, and `evolve` produce
local, structured evidence. Only `trace` executes generic argv, and only after
`--`. A natural-language claim is not command proof; `UNKNOWN` remains a
verification gap.

Real-host replay deliberately separates two data classes:

- **private raw rollout material** may contain host stdout/stderr, transcripts,
  command output, and workspace copies. It stays in the rollout directory;
- **Evidence Only records** contain normalized phenomena, deviations, hashes,
  task/runner identity, evidence references, and decisions. Harvest and local
  federation do not export raw transcripts, complete shell output, secrets, or
  environment values.

Each Task v2 policy explicitly names environment variables that may reach a
runner. `PATH`, `HOME`, and credentials such as `OPENAI_API_KEY` are not
implicitly inherited. For process adapters such as Codex and Claude Code,
credentials require the Task allowlist and `HOME` requires both that allowlist
and runner `inherit_home: true`; runner configuration may restrict Task
permission but cannot expand it. The scripted adapter ignores
`inherit_home` and other runner-config environment permissions and passes only
the Task `environment_allowlist`. Allowlisting an environment name does not
make its value public evidence.

All current host and scripted adapters report partial network isolation unless
they actually provide an OS-level boundary. A Task that requests
`enforced-deny` is rejected before execution on a partial adapter. Fixture
copying rejects root and nested symbolic links and special files through
no-follow directory descriptors. Observed Trace credit requires structured
argv through the injected `./.aet-rollout/bin/aet trace` executable. The scorer
recomputes the Git snapshot while excluding the Trace JSON itself; `UNKNOWN` or
mismatched snapshots fail. Declared artifacts and stdout/stderr logs must bind
to real non-link workspace files with matching source hashes, sizes, and fresh
`CREATED`/`CHANGED` state. Log paths must be the fixed paths derived from the
Trace output, artifact inline content is independently redacted again, and the
outer child argv, Trace argv, and intent proof command must be exactly equal.
Proof `evidence` must be an array.
Command text or an arbitrary JSON object does not count as evidence.

## Deterministic Quality layer

`aet quality diagnose` consumes a structured report plus an exact
`quality-mapping/v1` policy. It preserves each source `FAIL` or `UNKNOWN` and
maps a phenomenon code to an explicit owner, action, repair surface,
confidence, and human-review route. Missing mappings remain unresolved. This
is deterministic policy lookup and evidence routing—not semantic RCA, an
Evidence Graph, an LLM Judge, causal inference, or automatic responsibility
assignment.

`aet quality promote` accepts one confirmed badcase, the matching current
diagnosis, and the same mapping policy. It can stage a canonical validation-only
Learn Task v2 bundle with a copied fixture and quality sidecar. It deduplicates
identical canonical cases and accumulates support metadata, but does not perform
semantic clustering. It cannot write core, held-out, adversarial, or production
paths and does not repair the underlying asset.

## Learn Task v2 and observed evaluation

A Task v2 binds its prompt, fixture tree, runner, network statement, command and
change budgets, allowed write paths, expected tools, ordered calls, argument
constraints, proof IDs, artifacts, claims, and hard/soft scoring requirements.
`aet learn suite verify` checks the task and fixture integrity without claiming
that an Agent ran.

Scripted, Codex, and Claude Code runners are opt-in and apply only to Skill
behavior evaluation. Every baseline/candidate rollout uses a fixture copy and
normalized events. Repeated runs report per-task/per-variant:

- any-success (at least one PASS) and all-success (every run PASS);
- success rate and a 95% Wilson interval;
- paired baseline/candidate counts and an exact McNemar p-value;
- hard regressions, unusable infrastructure pairs, `INCONCLUSIVE`, and
  `INFRASTRUCTURE_ERROR` separately.

These statistics describe the declared suite and runner sample. They do not
establish universal Agent quality, eliminate evaluator bias, or turn a smoke
fixture into a general benchmark.

## Evolution Constitution and supported targets

Candidate IR v2 binds target type/path, baseline/candidate hashes, one to three
allowlisted operations, source patterns, budgets, adoption mode, and the
canonical Constitution hash. Evaluator code, evidence-state meanings, formal
suite partitions, and the human-adoption requirement are outside the candidate
write surface. This limits candidate influence; it is not a guarantee that an
evaluator or dataset is unbiased or impossible to game.

| Target | Allowed candidate surface | Evaluation and adoption boundary |
| --- | --- | --- |
| `skill` | Existing named editable blocks | Static document contract or opt-in real-host paired rollout. |
| `audit-rule` | Non-executable RulePack entries using allowlisted detectors | Four fixture partitions, then candidate-bound Shadow evidence before adoption. |
| `audit-profile` | Monotonic severity/sensitive-path changes and pre-approved exclusions | Deterministic policy suites; cannot disable a rule or lower severity. |
| `review-policy` | Smaller budgets and added sensitive paths/proofs | Deterministic suites; does not replace Intent. |
| `trace-validator` | Safe JUnit/SARIF/coverage/JSON assertions | Only fresh, explicitly declared Trace artifacts. |
| `triage-policy` | Non-negative weights and critical paths | Ordering only; finding status and visibility remain unchanged. |

Audit Rule Shadow never affects official findings or exit status. Adoption
requires an aggregate bound to the same candidate with the configured run,
repository, date, confirmation, and false-positive thresholds. Repository tests
exercise this logic with synthetic aggregates; that is not evidence that a
release has accumulated real multi-repository Shadow observations.

## Stage, adoption, and release

Gate results are metric vectors, not a general trust score. Only a qualifying
target-specific `PASS` may stage. Stage copies a hash-verified candidate for
review. `adopt --yes` separately rechecks the candidate, Gate, Constitution,
current baseline, and Decision Ledger update. It never commits or pushes.
`sleep` remains bounded and stage-only.

The repository also defines a manual real-host release gate. It builds the
tracked Skill candidate, runs six paired Codex rollouts over separated core,
validation, and held-out proof suites, and only after an observed PASS creates
a manifest bound to the Git commit, package version, candidate, raw gate, and
every task/fixture file. Release automation downloads that artifact for the
same workflow-run commit, reconstructs the candidate at the tag, and recomputes
the bindings. This is a release mechanism, not a claim that the external run
for v1.9.0 has already happened or passed.

## Explicit non-goals

AET does not present itself as a general Agent benchmark, an LLM-Judge-centric
evaluation platform, automatic RCA/Evidence Graph system, semantic clustering
service, Skill quality-YAML convention, auto-fix or auto-release agent, hosted
observability product, online business-metrics platform, or ticket/work-order
system. Other tools may own those jobs and consume or produce evidence that AET
can bind to a local engineering decision.
