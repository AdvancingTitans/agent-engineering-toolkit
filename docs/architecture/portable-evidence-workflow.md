# Portable evidence workflow

## Goal

The portable evidence workflow turns heterogeneous Agent run exports into
bounded, inspectable engineering evidence that another reviewer can consume
without installing AET.

```text
native Agent run
  -> Canonical Run Records
  -> Observations
  -> Evidence Candidates
  -> deterministic verification
  -> Portable Claims and Evidence
  -> Portable Evidence Bundle
  -> independent reviewer judgment
  -> optional Review Result validation
  -> human action
```

The workflow is an evidence interchange path, not a general multi-Agent
orchestrator. It does not select Agents, manage conversations, edit code,
resolve disagreements, merge changes, or publish releases.

## Authority boundaries

| Layer | Owns | Does not own |
|---|---|---|
| Native Agent runtime | Original run export | Portable evidence semantics |
| Run normalizer | Stable record shape, identity, linking, diagnostics | Tool authenticity or current workspace state |
| Investigator | Question, competing hypotheses, bounded read-only search, candidate generation | Code writes or evidence promotion |
| Deterministic evidence tools | Git, file, command receipt, Proof, and Freshness facts | Final review judgment |
| Bundle compiler | Selection, redaction, references, hashes, JSON/JSONL/Markdown projections | Source authenticity or reviewer decision |
| Reviewer | Independent, cited engineering judgment | Mutation of Bundle Evidence |
| Human or authorized host | Whether to act | Retroactive rewriting of historical evidence |

## Stage 1: normalize a run

```bash
aet run normalize \
  --source claude-code \
  --input native-run.jsonl \
  --run-group-id task-123 \
  --generation-id generation-001 \
  --output normalized-run/
```

Normalization emits six record types, stable identity metadata, tool-call
links, and diagnostics. It records the native export; it does not verify the
claims inside the export.

Incremental import accepts partial chunks plus prior normalized state. One
logical source generation must retain its run-group and generation identity.
File replacement or truncation requires a new generation.

## Stage 2: bounded investigation

```bash
aet investigate \
  --request investigation-request.json \
  --run normalized-run/ \
  --output investigation-result.json

aet investigate \
  --request investigation-request.json \
  --run normalized-run/ \
  --workspace . \
  --proof .aet/proof.json \
  --output verified-investigation-result.json
```

The portable investigator is a read-only runtime. Its policy requires:

- a read-only workspace;
- no arbitrary command execution;
- no write, commit, push, merge, reset, checkout, or publish tools;
- a primary and at least one competing hypothesis;
- disconfirming search;
- explicit record, candidate, evidence, tool-call, and Blob budgets;
- privacy controls for secret redaction, reasoning export, and raw tool output.

It always extracts Observations and Evidence Candidates and records a Ledger.
Without explicit verification inputs it stops as `unknown`. When the host
supplies a local AET Proof, the policy explicitly allows `proof.inspect` and
`freshness.check`, and the Proof command matches a recorded command Candidate,
the deterministic verifier may mark that Candidate `verified` and emit bound
Verified Evidence. The verifier checks that both the Proof path and recorded
workspace remain inside and match the declared workspace. It never reruns the
recorded Agent command implicitly. Missing, stale, unmatched, unauthorized, or
over-budget verification remains bounded and cannot produce a current
`supported` Claim.

## Observation and Evidence separation

An Observation says what the normalized run contains. It must include:

- `proves`: the smallest proposition supported by the record itself;
- `does_not_prove`: likely but unsupported inferences;
- `source_refs`;
- `limitations`.

Examples:

- an Agent statement proves only that the statement was recorded;
- a tool call proves only that the call appears in the run;
- a tool result proves only that the output appears in the run;
- metadata proves only that the run declared those values.

An Evidence Candidate remains `unverified` until a deterministic verifier
binds it to relevant source, workspace, code, command, environment, and
Freshness facts. A matching Proof can verify a command Candidate; Agent
self-report and recorded tool output are never promoted merely because their
text appears plausible.

## Stage 3: deterministic verification

The broader AET evidence core can produce facts such as Git state, file
content, command receipts, Proof results, and Freshness comparisons. Evidence
strength remains discrete:

```text
context_only < observed < corroborated < reproduced
```

No count of weak Observations is equivalent to reproduced evidence.
Freshness changes present applicability while preserving the historical
record.

## Stage 4: compile a Bundle

```bash
aet bundle create \
  --investigation investigation-result.json \
  --output evidence-bundle/
```

An observation-only result compiles to an `unknown` Claim with Observations and
sources, not fabricated Verified Evidence. A deterministically verified result
compiles the Proof Source, Freshness, Candidate bindings, Ledger entries, and
Verified Evidence into the same portable format. A complete compiler payload
can also include Counter-evidence, conflicts, diagnostics, and
content-addressed Blobs.

The compiler selects a question-focused closure:

- referenced Claims;
- their supporting and Counter-evidence;
- referenced Observations and sources;
- related conflicts, diagnostics, Ledger entries, and Blobs.

It writes `Index`, `Core`, and `Archive` layers, applies configured redaction,
seals file and Blob hashes, validates the result, and refuses to replace an
existing output directory.

## Index, Core, and Archive

`index.json` is the minimal entry point. It declares the question, references,
reading order, excluded-record count and reason, Archive availability, and
consumer guidance.

`core/` holds current-question Claims, Evidence, and Observations. `archive/`
holds source provenance, diagnostics, conflicts, and the investigation Ledger.
`blobs/` holds complete content addressed by SHA-256 when a model-facing view
is truncated or an Artifact is externalized.

Consumers should open Archive or Blobs when:

- a Claim is `conflicted`;
- Freshness is `unknown` or stale;
- a source uses content identity;
- a tool output is truncated;
- a diagnostic affects the cited record;
- the investigation path needs to be challenged.

## Stage 5: validate and render

```bash
aet bundle validate evidence-bundle/

aet bundle render \
  --bundle evidence-bundle/ \
  --format markdown \
  --output evidence-report.md
```

Validation checks strict protocol fields, paths, file and Blob hashes,
reference closure, Counter-evidence, conflicts, budgets, Grounding,
Freshness, and privacy policy. The loader rejects symbolic links, special
files, escaping paths, duplicate JSON keys, and Blob budgets that exceed
either the caller or Bundle limit.

The Markdown report is a deterministic projection of the validated Bundle. It
cannot add stronger facts than the JSON records.

## Stage 6: independent review

A reviewer reads the Bundle and produces its own judgment. It must cite Claim
and Evidence IDs, disclose Counter-evidence, preserve `unknown` and
`conflicted`, and check Freshness.

The optional Portable Review Result validator checks those reference
boundaries. It does not make the judgment and does not grant authority to act.

## Security limits

SHA-256 detects content mutation relative to the Manifest. It does not prove
who created the Bundle, authenticate a native run, or establish that an
external tool actually executed. Portable Evidence Bundle v1 has no signature
or trust-root mechanism.

See [Evidence Bundle threat model](../security/evidence-bundle-threat-model.md)
and [Run Record redaction](../privacy/run-record-redaction.md).
