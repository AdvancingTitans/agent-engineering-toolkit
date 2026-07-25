# Run Record redaction

## Boundary

Canonical Run Records are investigation inputs, not automatically public
artifacts. They can contain user messages, Agent statements, tool arguments,
tool output, workspace paths, model metadata, and private reasoning.

Secret redaction is applied when material is compiled into a Portable Evidence
Bundle. The normalizer does not silently rewrite source text because doing so
would change stable semantic identity and make source relationships ambiguous.

## Default handling

- Keep native runs and normalized-run directories private.
- Mark reasoning records `public_export_allowed: false`.
- Do not use reasoning as factual Evidence.
- Keep diagnostic messages independent of native text.
- Export only question-relevant records into Bundle Core and Archive.
- Do not export raw tool output or Blobs unless the policy allows it.

The portable investigator additionally enforces its request privacy policy:

```json
{
  "redact_secrets": true,
  "export_reasoning": false,
  "export_raw_tool_output": false
}
```

The read-only investigator applies these settings before persisting
Observations and Evidence Candidates. Deterministic Proof export retains only
the receipt bindings and hashes required by the Portable Evidence contract.

## Recognized secret classes

The deterministic Bundle redactor recognizes common assignments for API keys,
tokens, secrets, passwords, and authorization values, common bearer
credentials, and selected well-known token prefixes.

Matched values are replaced with `[REDACTED]`. Diagnostics do not include the
matched source text.

This is a bounded pattern set, not a proof that all sensitive values have been
found. Repositories with custom credential formats should add an external
review or avoid exporting the affected records.

## Stable reference fields

IDs, task and workspace identifiers, investigation and Bundle IDs, source
references, Evidence references, Counter-evidence references, Observation
references, support relationships, hypothesis references, and hashes are
stable protocol fields.

If recognized secret material appears inside one of these fields, the compiler
fails closed. It does not replace part of the reference, because that would
break identity and reference closure.

The safe remedy is to regenerate the upstream identifier without secret
material and produce a new normalized run or investigation.

## Blob redaction

When `redact_secrets` is true:

1. every selected Blob must decode as UTF-8;
2. recognized secrets are replaced in the decoded text;
3. the transformed bytes receive a new SHA-256;
4. the Blob path changes to `blobs/sha256-<new-digest>`;
5. Evidence and Source references are rebound to the new path and hash;
6. byte counts are updated when the schema includes them.

The original Blob bytes are not retained in the compiled Bundle.

Non-UTF-8 selected Blobs fail closed under redaction policy because the
implemented redactor cannot safely inspect them. A host may omit the Blob or
use a separately reviewed transformation before compilation.

## Truncated content

A model-facing Evidence view may be truncated, but truncation is not
redaction. A truncated Evidence record must keep:

- `truncated: true`;
- `original_bytes`;
- a `blob_ref`;
- the complete exported Blob's `content_hash`.

If policy forbids raw tool output or Blob export, the producer must not pretend
that a truncated view has a complete backing Blob. The Claim must preserve the
resulting limitation or remain `unknown`.

## Paths and metadata

Working directories, repository locations, branch names, and model fields are
historical run declarations. They can reveal local usernames, project names,
or infrastructure layout.

Only include these fields when they are required by the investigation.
Portable Sources should prefer task-relative, repository-relative, or
content-addressed locators where the schema permits them. Redacting a displayed
path does not create a current workspace binding.

## Reasoning

Reasoning may help a private investigator propose hypotheses or find a
contradiction. It cannot prove code, command, authorization, or Freshness
facts.

Canonical reasoning records always declare `public_export_allowed: false`.
Portable Bundle compilation should leave them out unless an explicit private
workflow has a separate, reviewed need. Even then, they remain Observations
with a non-empty `does_not_prove` boundary.

## Review before distribution

Before sharing a Bundle outside the originating environment:

- [ ] Validate all file and Blob hashes.
- [ ] Confirm the privacy policy has `redact_secrets: true`.
- [ ] Search the compiled output for organization-specific credential formats.
- [ ] Review Source locators and workspace metadata.
- [ ] Confirm reasoning is absent.
- [ ] Confirm raw tool output and Blobs are necessary.
- [ ] Confirm diagnostics do not echo native content.
- [ ] Confirm the recipient needs only Index/Core, or intentionally include
      Archive and Blobs.

Hash validation detects mutation after export. It does not certify that
redaction is complete.
