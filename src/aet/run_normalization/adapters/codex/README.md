# Codex Source Adapter Contract

This adapter maps supported Codex run events into
`canonical-run-record/1.0`. It is a format adapter only: a normalized tool
record proves what the source run contains, not that the tool ran in the
current workspace.

## Accepted source format

- Input must be a readable, regular, non-symbolic-link UTF-8 file.
- The shared Normalizer accepts either JSONL with one JSON object per
  non-empty line or one top-level JSON array of objects.
- Supported event families are:
  - `session_meta` and `turn_context`;
  - `response_item` and `event_msg`;
  - completed streamed items: `item.completed`;
  - top-level `user` and `assistant` events whose `content` is a string.
- Supported `response_item` / `event_msg` payload types are:
  - `message`, `user_message`, `agent_message`;
  - `reasoning`, `agent_reasoning`;
  - `function_call`, `custom_tool_call`;
  - `function_call_output`, `custom_tool_call_output`.
- Supported completed item types are `command_execution`, `mcp_tool_call`,
  `tool_call`, and `agent_message`.

Malformed JSON and non-object entries do not become Run Records. The shared
Normalizer emits a privacy-safe `malformed_record` diagnostic and continues
with the remaining input.

## Run group and record identity

Run group candidates are read from `thread_id`, `session_id`, or `run_id` on
the event or its `payload`. A `session_meta.payload.id` is also a candidate.
An explicit CLI `--run-group-id` remains authoritative; conflicting native
groups produce `run_group_conflict`.

For non-Meta records, native identity is chosen from the first non-empty
`id`, `uuid`, `call_id`, or `item_id` found on `payload`, then the event.
Completed streamed items prefer `item.id`. Meta identity is always
`synthetic`, because it describes deterministic run context rather than one
portable message.

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

- `session_meta` / `turn_context` become Meta records containing supported
  `cwd`, Git branch, and model strings.
- User and assistant messages become one corresponding message record.
- Supported text blocks in a message content array are concatenated in source
  order.
- Reasoning payloads become Reasoning records with
  `public_export_allowed: false`.
- Supported tool calls and results become separate Tool Call and Tool Result
  records.
- Valid timestamps are retained. Missing or invalid timestamps are replaced
  with a deterministic placeholder and reported by diagnostics.

The adapter preserves only canonical fields required by these records. It does
not retain the complete native event.

## Records discarded

- Unknown event and payload types are discarded with `unsupported_record`.
- `item.started` and `item.updated` are not retained; only `item.completed`
  supplies a completed streamed item.
- Messages whose role is neither `user` nor `assistant` are discarded.
- Unsupported content block types and native envelope fields are not copied.
- No hidden or unsupported record is silently converted into a known type.

Discarding an unsupported record does not copy its raw content into the
diagnostic message.

## Tool call and result handling

- `function_call` and `custom_tool_call` use `call_id` or `id`, plus `name` or
  `tool`.
- `function_call_output` and `custom_tool_call_output` use `call_id` or
  `tool_call_id`.
- A completed `command_execution` produces a `shell` Tool Call and a Tool
  Result containing `exit_code` and `aggregated_output`.
- A completed `mcp_tool_call` / `tool_call` produces a Tool Result only when
  the item contains `result` or `output`.
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

Tool output remains recorded behavior and is not promoted to reproduced
Evidence.

## Unknown fields and extensions

Unknown native fields are ignored rather than copied into an extension bag.
Unknown event shapes produce `unsupported_record` when they yield no supported
component. Flags named `truncated`, `output_truncated`, or `repaired` anywhere
in a source event produce explicit diagnostics, but do not authorize silent
repair.

This adapter does not infer semantics from future field names. A new native
shape requires an explicit adapter change and clean/failing Fixtures.

## Known version differences

Adapter version `1.0.0` intentionally covers two observed Codex shape
families: rollout-style `session_meta` / `response_item` / `event_msg` records
and completed streamed `item.completed` records. Field aliases documented
above are supported to keep those families canonical.

There is no product-version negotiation or guarantee for every historical or
future Codex release. Streaming deltas are not assembled, and unknown future
event types remain `unsupported_record`. The normalized Manifest records the
Normalizer version, canonical schema version, Adapter version, and
configuration hash so consumers can identify the exact interpretation used.

## Privacy

- Diagnostics contain stable codes and locations, never raw unsupported source
  text.
- Reasoning is retained only as a private Run Record and is marked
  `public_export_allowed: false`; Bundle export policy must still exclude it by
  default.
- Message text, `cwd`, tool arguments, and tool results may contain repository
  paths, credentials, tokens, user data, or command output. Normalization is
  not a complete redaction boundary.
- Treat native input and normalized output as sensitive. Apply the Bundle
  Compiler's privacy policy and secret redaction before portable export.
- Do not publish raw runs or complete tool output merely because normalization
  succeeded.
