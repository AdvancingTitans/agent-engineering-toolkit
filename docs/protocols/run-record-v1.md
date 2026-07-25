# Canonical Run Record v1

## Purpose

Canonical Run Record v1 is the host-neutral input format for bounded
investigation. It converts supported native Agent run exports into a stable
set of messages, tool calls, tool results, metadata, and normalization
diagnostics.

The format records what a run export contains. It does not prove that a tool
ran in the current workspace, that a result is authentic or complete, that a
command was authorized, or that historical output still applies.

The normative schemas are:

- `schemas/run-record/v1/run-record.schema.json`
- `schemas/run-record/v1/run-manifest.schema.json`
- `schemas/run-record/v1/diagnostics.schema.json`

## Output layout

```text
normalized-run/
├── manifest.json
├── records.jsonl
└── diagnostics.jsonl
```

`manifest.json` binds the source type, run group, generation, partial-input
state, base byte offset, normalizer provenance, and output counts.
`records.jsonl` contains one `canonical-run-record/1.0` object per line.
`diagnostics.jsonl` contains non-secret parsing and quality diagnostics.

The current implementation accepts `codex` and `claude-code` native sources.
Adapters are source-specific, while their output record and identity semantics
are shared.

## Record types

| `record_type` | Required payload | Evidence meaning |
|---|---|---|
| `meta` | `source_type` | Historical metadata declared by the run |
| `user` | `content` | User content present in the exported run |
| `assistant` | `content` | Agent statement present in the exported run |
| `reasoning` | `content`, `public_export_allowed: false` | Investigation context only |
| `tool_call` | `tool_call_id`, `tool_name`, `arguments_json` | A recorded call, not execution proof |
| `tool_result` | `tool_call_id`, `linked_tool_call_record_id` | A recorded result, not current proof |

Every record also has a 64-character lowercase SHA-256 `record_id` and a
`source_identity`. A retained timestamp is an ISO 8601 value. When a valid
native timestamp is unavailable, the normalizer emits a deterministic
placeholder and a `synthesized_timestamp` diagnostic.

Reasoning records are explicitly marked `public_export_allowed: false`.
Portable exports must not use them as factual Evidence.

## Stable identity

`source_identity` contains:

```json
{
  "run_group_id": "run-123",
  "stable_source_record_id": "native-or-derived-id",
  "identity_kind": "native",
  "source_order_id": "00000000000000000042:0000",
  "record_id": "…",
  "content_hash": "…"
}
```

Identity kinds have decreasing source guarantees:

1. `native`: the native run supplied a stable event or message identifier.
2. `location`: identity is bound to a generation and source location.
3. `content`: neither native nor generation-bound location identity was
   available; semantic content is used as a deduplication fallback.
4. `synthetic`: the normalizer deterministically created the record, such as a
   metadata record.

`record_id` identifies the logical normalized component. `content_hash`
identifies its semantic content. Importing the same stable identity with
different semantic content fails closed rather than silently replacing the
earlier record.

Content identity is weaker than native or location identity: equivalent
content can deduplicate, but the format cannot reliably distinguish two
separate logical events with identical content. Consumers must preserve the
`content_identity_fallback` diagnostic.

## Tool linking

Tool calls and results are joined by `tool_call_id`.
`linked_tool_call_record_id` points from a result to the matching normalized
call when one is available.

- An unmatched result remains a record and receives
  `orphan_tool_result`.
- A call without a result receives `missing_tool_result` for a complete run.
- A partial run does not claim that a missing result will never arrive.
- A duplicate result for the same call is diagnosed and ignored.
- Invalid tool arguments are represented by canonical `null` arguments and
  receive `invalid_tool_arguments`.

Linking is a record relationship. It does not authenticate either side or
prove execution.

## Incremental normalization

Long native runs can be normalized in chunks:

```bash
aet run normalize \
  --source codex \
  --input chunk-1.jsonl \
  --run-group-id run-123 \
  --generation-id generation-001 \
  --partial \
  --output normalized-1/

aet run normalize \
  --source codex \
  --input chunk-2.jsonl \
  --run-group-id run-123 \
  --generation-id generation-001 \
  --base-byte-offset 4096 \
  --prior normalized-1/ \
  --output normalized-2/
```

`base_byte_offset` anchors source-order locations for the supplied chunk; it is
not a request to seek into the input file. The caller supplies only the chunk
whose first byte has that absolute offset.

The same `run_group_id` and `generation_id` must be used while extending one
logical source generation. Reimporting the same chunk is idempotent. Tool calls
and later results can link across the prior/current boundary.

When `partial` is true and no explicit generation is supplied, location
identity is not sufficiently stable and the implementation falls back to
content identity. A truncated, replaced, or restarted source file must use a
new generation instead of reusing offsets from the previous file.

## Manifest and provenance

The manifest records:

- `source_type`
- `run_group_id`
- `generation_id`
- `partial`
- `base_byte_offset`
- `provenance.normalizer_version`
- `provenance.schema_version`
- `provenance.adapter_name`
- `provenance.adapter_version`
- `provenance.configuration_hash`
- record and diagnostic counts

The configuration hash covers the source type, partial flag, base offset, and
generation. It makes normalization settings traceable; it is not a signature
and does not establish who produced the native run.

## Diagnostics

Diagnostics are stable, content-free summaries of degraded input or recovery
conditions. v1 includes malformed or unsupported records, run-group conflicts,
source-record conflicts, missing or duplicate tool results, invalid arguments
or timestamps, synthesized timestamps, declared truncation, declared repair,
content-identity fallback, and partial-run state.

Diagnostic messages intentionally do not echo native record content or secret
values. A diagnostic can affect how an Observation is consumed even when the
corresponding record remains available.

## Metadata and ordering limitations

Metadata is a historical declaration by the exported run:

- `working_directory` is not proof of the current process directory.
- `git_branch` is not a current Git binding.
- `model` is not independently authenticated.
- a metadata record uses synthetic identity.

`source_order_id` provides deterministic normalized ordering. It is not a
wall-clock timestamp and does not prove that the native export is complete.
Synthesized timestamps preserve deterministic serialization only; consumers
must not use them to infer execution duration or real event order.

## Privacy boundary

Normalization preserves relevant native text so that later investigation can
inspect it. The normalized-run directory is therefore not automatically safe
to publish.

- Reasoning is retained with `public_export_allowed: false`.
- Diagnostics do not include native text.
- Secret redaction is performed at the portable export boundary, not by
  silently mutating stable Run Record identities.
- Keep normalized runs private unless their content has been reviewed.

See [Run Record redaction](../privacy/run-record-redaction.md) for the export
boundary.

## Inspection

```bash
aet run inspect --run normalized-run/ --format json
aet run inspect --run normalized-run/ --tool-calls --format jsonl
```

Inspection is read-only. Its output still has Run Record semantics and must not
be presented as Verified Evidence.
