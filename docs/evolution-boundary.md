# Evidence-Gated Evolution boundary

`aet learn` is a local engineering-improvement loop. It learns from structured
AET evidence, not from an unbounded transcript archive, and it never turns a
proposal into a production change by itself.

## What is immutable

The canonical Skill marks immutable and editable regions explicitly. A
candidate may modify only a named `aet-learn:editable` block. Gate 0 rejects a
candidate that changes any other byte, its target, its baseline hash, or its
Patch IR budget.

- `UNKNOWN` is never a pass.
- Only `aet trace -- <argv>` executes a command.
- `audit`, `review`, and Evidence Pack compilation do not execute proof commands.
- A context `--read` declaration is an attestation, not proof of comprehension.
- Propose, replay, gate, and stage are not adoption.
- Adoption, commit, push, remote sharing, and transcript retention require an explicit human action.

## Evidence and privacy

The default profile is **Evidence Only**. `harvest` reads local AET JSON,
finding IDs, report hashes, snapshots, and rejection records. It does not read
raw prompts, transcripts, shell output, environment variables, secrets, or
undeclared file content. `collect` accepts only Evidence Only packs into a
user-controlled local store such as `~/.aet/experience/`; no command fetches
or uploads that store.

`inspect`/`summarize` are deterministic pre-proposal reports. `mine` records
support count, independent repository fingerprints, and distinct dates. A
pattern is HIGH only with five experiences from three repositories across two
dates; MEDIUM needs three experiences. These are transparent support rules,
not an LLM confidence score.

## Candidate and model authority

The [`learn-candidate` schema](../schemas/learn-candidate.schema.json) fixes
the Patch IR surface: one to three replacements of existing editable blocks,
with before hashes and character limits. `propose --engine rules` is the
default. `--engine model` is opt-in and requires an explicit local argv,
timeout, bounded JSON input/output, and optional local rejected-candidate
records. A model cannot change evidence, define a gate, adopt a candidate, or
run a shell command through AET.

## Replay and Gates

`replay --runner static` writes baseline and candidate copies into a temporary
directory and uses the built-in deterministic Skill-document runner. Its metric
names begin with `static_contract_`; it is a cheap Gate 0, not observed Agent
behavior.

`replay --runner scripted|codex|claude-code` creates a separate fixture copy
for each baseline/candidate rollout. The runner records normalized JSONL events,
private raw stdout/stderr hashes, final response, and before/after snapshots.
The deterministic scorer checks actual command events, Trace output, artifact
paths, workspace scope, and final claims. It never treats a host exit code or a
textual “I read the Skill” assertion as task success. Learn Task v2 uses
[`learn-task-v2`](../schemas/learn-task-v2.schema.json); normalized event
records follow [`learn-agent-run`](../schemas/learn-agent-run.schema.json).

Codex and Claude adapters are opt-in local processes. They do not install or
log in to a host, do not read host history, and keep full output out of Evidence
Only experiences. Their workspace isolation protects the production checkout,
but AET reports network isolation and command allowlisting as `PARTIAL` unless
an external sandbox proves stronger controls.

Every Gate requires all of the following:

1. target/hash/editable-region/Patch IR checks;
2. a static candidate audit in a temporary copy;
3. no regression in the immutable core suite;
4. no overlap between validation and held-out task bytes;
5. no validation or held-out regression and at least one independent improvement;
6. token, command-surface, and workflow-overuse limits;
7. explicit human review before `adopt --yes`.

An observed `adoptable` Gate additionally requires paired baseline/candidate
rollouts, at least five usable pairs, zero safety regressions, an absolute task
gain of at least 0.05, and two-sided exact McNemar `p <= 0.05`. Small samples
are `INCONCLUSIVE`, and host startup/auth/model failures are
`INFRASTRUCTURE_ERROR`; neither can stage. `tournament` opens held-out only for
the constraint-ranked finalist and prefers the smallest rules candidate when
effects are tied.

The report is a metric vector, never an agent-trust score. `viewer` produces a
static, no-network HTML review artifact for the Gate.

## Cross-project and Sleep operation

Multiple repositories may add de-identified packs with `collect`; users merge
them with `harvest --experience-store`. The store is local and is never
silently shared.

`sleep` performs `harvest → mine → propose → replay → gate → stage` and writes
an append-only `learning-run.json` with `run_type: SKILL_EVOLUTION` and state
events. Its default policy is one candidate, the static runner, preliminary
statistics, two replay suites, at most one model call, and a 120-second
wall-clock budget. A real runner and an adoptable profile are explicit inputs;
even then Sleep only stages a passing candidate. It checks that the production
target has not changed, writes only under its output directory until a human
runs `adopt --yes`, and never commits, pushes, schedules itself, or uploads
data. A scheduler may invoke it, but should pass explicit limits and keep the
production repository read-only.

## Feedback and experiences

`aet learn feedback record` stores only accepted/rejected outcome, reason codes,
run/task/candidate hashes, and corrected-behavior structure. It hashes optional
human free text instead of retaining it. `harvest` may turn this compact record
or an observed score into an Evidence Only experience. Mining records distinct
task and runner counts; static-only records cannot establish HIGH confidence.
