# Claude Code Source Adapter Contract

This adapter maps supported Claude Code run events into
`canonical-run-record/1.0`. It standardizes recorded behavior only; it does not
turn an Agent message or Tool Result into current-workspace proof.

## Accepted source format

- Input must be a readable, regular, non-symbolic-link UTF-8 file.
- The shared Normalizer accepts either JSONL with one JSON object per
  non-empty line or one top-level JSON array of objects.
- Supported event types are `system`, `user`, `assistant`, and `result`.
- A `result` event is supported only when its `result` field is a string.
- `user` and `assistant` content may be:
  - a string on `message.content` or the event's `content`; or
  - an array containing `text`, `thinking`, `tool_use`, and `tool_result`
    blocks.

Malformed JSON and non-object entries do not become Run Records. The shared
Normalizer emits a privacy-safe `malformed_record` diagnostic and continues
with the remaining input.

## Run group and record identity

Run group candidates are read from `session_id`, `conversation_id`, or
`run_id` on the event or nested `message`. An explicit CLI `--run-group-id`
remains authoritative; conflicting native groups produce
`run_group_conflict`.

For non-Meta records, native identity is chosen from the first non-empty `id`,
`uuid`, or `message_id` on `message`, then the event. A content block's `id`
takes precedence for that block. Meta identity is always `synthetic`, because
it describes deterministic run context rather than one portable message.

When no native identity exists:

1. a complete import, or a partial import with an explicit `generation_id`,
   uses the absolute byte/record location (`location`);
2. a partial import without an explicit generation uses semantic content
   identity (`content`) and emits `content_identity_fallback`.

`record_id` binds the selected Run Group, generation, stable source identity,
and semantic component key. `content_hash` covers semantic record content.
The same stable identity with different content fails closed. Replacing or
truncating the source file requires a new generation.

## Records retained

- A `system` event becomes a Meta record containing supported `cwd`, Git
  branch, and model strings.
- String content becomes one User or Assistant message record.
- All `text` blocks in one event are concatenated in source order into one
  User or Assistant message record.
- Each `thinking` block becomes a separate Reasoning record with
  `public_export_allowed: false`.
- Each supported `tool_use` and `tool_result` block becomes a separate Tool
  Call or Tool Result record.
- A supported string `result` event becomes an Assistant record with semantic
  component `result`.
- Valid timestamps are retained. Missing or invalid timestamps are replaced
  with a deterministic placeholder and reported by diagnostics.

The adapter preserves only canonical fields required by these records. It does
not retain the complete native event or all content-block attributes.

## Records discarded

- Event types other than `system`, `user`, `assistant`, and supported string
  `result` are discarded with `unsupported_record`.
- A `user` / `assistant` event whose content is neither a string nor an array
  is discarded.
- Non-object content array entries and unknown block types are ignored.
- If an event yields no supported component, the shared Normalizer emits
  `unsupported_record`.
- Unsupported block attributes, including fields not mapped into the
  canonical Tool Result, are not copied.
- No hidden or unsupported record is silently converted into a known type.

Discarding unsupported input does not copy its raw content into diagnostics.

## Tool call and result handling

- A `tool_use` block uses its `id` as Tool Call ID, `name` as Tool Name, and
  `input` as arguments.
- A `tool_result` block uses `tool_use_id` to link back to the Tool Call and
  stores `content` as the result.
- Arguments are valid only when they are an object/array, or a JSON string
  decoding to an object/array. Invalid arguments become canonical `null` and
  emit `invalid_tool_arguments`; they are never guessed or repaired.
- Matching is by non-empty Tool Call ID, including across incremental chunks.
  A matched result receives `linked_tool_call_record_id`.
- An orphan result is retained with `orphan_tool_result`. The first result for
  a call is retained; later results are ignored with
  `duplicate_tool_result`.
- A final, non-partial import reports `missing_tool_result` for a call without
  a result. Partial imports defer that diagnostic.

Fields such as `is_error` are not currently promoted into separate canonical
semantics. Consumers must inspect the retained result content or stronger AET
evidence; they must not infer success merely from the presence of a Tool
Result.

## Unknown fields and extensions

Unknown native fields are ignored rather than copied into an extension bag.
Unknown event shapes produce `unsupported_record` when they yield no supported
component. Flags named `truncated`, `output_truncated`, or `repaired` anywhere
in a source event produce explicit diagnostics, but do not authorize silent
repair.

This adapter does not infer semantics from future field names. A new native
shape requires an explicit adapter change and clean/failing Fixtures.

## Known version differences

Adapter version `1.0.0` covers the documented `system` / `user` / `assistant`
/ `result` JSONL family and the supported message content blocks listed above.
It accepts content at either `message.content` or event `content`, and accepts
native identity on the nested message or event.

There is no product-version negotiation or guarantee for every historical or
future Claude Code release. Streaming deltas are not assembled, and unknown
future block or event types are ignored or reported as `unsupported_record`.
The normalized Manifest records the Normalizer version, canonical schema
version, Adapter version, and configuration hash so consumers can identify the
exact interpretation used.

## Privacy

- Diagnostics contain stable codes and locations, never raw unsupported source
  text.
- `thinking` content is retained only as a private Reasoning Run Record and is
  marked `public_export_allowed: false`; Bundle export policy must still
  exclude it by default.
- Message text, `cwd`, Tool Input, and Tool Result content may contain
  repository paths, credentials, tokens, user data, or command output.
  Normalization is not a complete redaction boundary.
- Treat native input and normalized output as sensitive. Apply the Bundle
  Compiler's privacy policy and secret redaction before portable export.
- Do not publish raw runs or complete Tool Result content merely because
  normalization succeeded.
