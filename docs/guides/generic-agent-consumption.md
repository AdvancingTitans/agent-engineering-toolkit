# Generic Agent consumption

## Baseline

A reviewer needs only a way to read JSON, JSONL, Markdown, and optional Blob
files. AET, Python, Node.js, and a dedicated SDK are not required.

Treat the Bundle as a structured source, not as final authority.

## Recommended reading order

1. Read `manifest.json`.
2. Check `protocol.name`, `protocol.version`, `bundle.id`, task binding, and
   investigation question.
3. Verify `integrity.file_hashes` if a SHA-256 implementation is available.
4. Read `index.json`, especially `reading_order`, `excluded`, and
   `consumer_guidance`.
5. Read `core/claims.jsonl`.
6. Resolve cited records in `core/evidence.jsonl` and
   `core/observations.jsonl`.
7. Open relevant `archive/` records and Blobs when a limitation, conflict,
   stale state, truncation, or degraded identity requires it.

`report.md` is a convenient deterministic projection. The JSON and JSONL
records remain the machine-readable source for IDs, references, Freshness, and
integrity fields.

## Interpret record classes correctly

### Observation

An Observation describes what a normalized run contains. Read both:

- `proves`
- `does_not_prove`

Do not cite the Observation for a proposition listed in `does_not_prove`.
Agent statements and recorded tool output are not current execution proof.

### Evidence

Check:

- `proposition`
- `kind`
- `strength`
- `source_refs`
- `bindings`
- `freshness`
- `supports` and `contradicts`
- `limitations`
- `integrity`

`context_only` and `observed` are weaker than `corroborated` and `reproduced`.
Even strong historical Evidence cannot prove the current workspace when its
Freshness is stale or unknown.

### Claim

Read the status, supporting Evidence, Counter-evidence, Observations, basis,
limitations, and smallest next action.

- `unsupported` does not mean false.
- `unknown` is not a negative fact.
- `conflicted` requires both sides to remain visible.

## Counter-evidence

For every cited Claim:

1. collect every ID in `counter_evidence_refs`;
2. read those Evidence records;
3. disclose them in the review conclusion;
4. explain whether the conflict is resolved or remains material.

Do not omit Counter-evidence because it does not fit the preferred conclusion.

## Freshness

Treat these statuses as follows:

| Status | Review treatment |
|---|---|
| `current` | May be applied within its declared bindings and limitations |
| `relevant_files_changed` | Historical result only; rerun affected verification |
| `workspace_changed` | Rebind or rerun in the current workspace |
| `environment_changed` | Recreate or explain the environment difference |
| `unknown` | Request a Freshness check or preserve uncertainty |

Freshness never rewrites the historical command or output.

## When to open Archive

Read `archive/diagnostics.jsonl` when normalization or export quality can
affect a cited record. Read `archive/conflicts.jsonl` for a `conflicted` Claim.
Read `archive/sources.jsonl` to inspect provenance and locator bindings. Read
`archive/ledger.jsonl` to see which question and hypothesis a bounded action
addressed.

Content identity, synthesized timestamps, partial runs, orphan results, and
truncated output are all reasons to narrow a conclusion or request more
evidence.

## Blob handling

Only read a Blob that is referenced by a relevant Evidence or Source record.
Check that:

- its path is `blobs/sha256-<digest>`;
- the bytes match the digest;
- the Bundle policy permits the total Blob bytes;
- a truncated Evidence record declares `original_bytes`.

Do not execute a Blob. Treat it as bytes or UTF-8 text according to the
declared source. A matching hash provides integrity, not authenticity.

## Review checklist

Before issuing a factual conclusion:

- [ ] The conclusion cites at least one Bundle Claim.
- [ ] Every supporting Evidence ID exists and supports that Claim.
- [ ] Every declared Counter-evidence ID is disclosed.
- [ ] Observation content is not described as Verified Evidence.
- [ ] No `does_not_prove` proposition has been promoted.
- [ ] Freshness is appropriate for the requested conclusion.
- [ ] `unknown` and `conflicted` states are preserved.
- [ ] Excluded records and stated limitations are not silently generalized.
- [ ] Additional investigation is requested when the required strength is
      unavailable.

## Optional structured result

Produce `portable-review-result/1.0` JSON when the host wants deterministic
reference validation:

```json
{
  "protocol": {"name": "portable-review-result", "version": "1.0"},
  "bundle_id": "bundle-001",
  "conclusions": [
    {
      "id": "review-001",
      "statement": "More investigation is required.",
      "disposition": "request_investigation",
      "claim_refs": ["claim-001"],
      "evidence_refs": [],
      "counter_evidence_refs": [],
      "reasoning_summary": "The Claim remains unknown.",
      "limitations": ["No current deterministic verification is present."],
      "next_action": "Run the authorized narrow verification command."
    }
  ],
  "unresolved_questions": ["Does the result apply to the current commit?"]
}
```

The host may validate it with:

```bash
aet bundle validate-review \
  --bundle evidence-bundle/ \
  --review review-result.json
```

Validation is optional for consumption and does not certify the implementation.
