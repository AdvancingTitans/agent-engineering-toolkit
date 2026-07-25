# Portable Review Result v1

## Purpose

Portable Review Result v1 lets any reviewer express conclusions grounded in a
Portable Evidence Bundle. The reviewer does not need AET installed to read the
Bundle or produce the JSON result.

The optional AET validator checks protocol shape, references, Counter-evidence,
Freshness, and evidence-strength boundaries. It does not decide whether the
implementation is correct and does not replace reviewer or human judgment.

The normative schema is
`schemas/evidence-bundle/v1/review-result.schema.json`.

## Document shape

```json
{
  "protocol": {
    "name": "portable-review-result",
    "version": "1.0"
  },
  "bundle_id": "bundle-001",
  "conclusions": [
    {
      "id": "review-conclusion-001",
      "statement": "The declared verification is supported for the bound workspace.",
      "disposition": "accept",
      "claim_refs": ["claim-001"],
      "evidence_refs": ["ev-001"],
      "counter_evidence_refs": [],
      "reasoning_summary": "The conclusion uses current corroborated evidence.",
      "limitations": ["No conclusion is made about excluded paths."]
    }
  ],
  "unresolved_questions": []
}
```

The root may contain an `extensions` object. Unknown fields outside that
namespace fail closed.

## Dispositions

| `disposition` | Meaning |
|---|---|
| `accept` | Accept the referenced conclusion within its declared limits |
| `request_change` | Request a change based on the referenced grounded Claims |
| `request_investigation` | Existing evidence is insufficient or requires a new bounded investigation |
| `unknown` | Preserve uncertainty without a definitive action judgment |

A disposition is not an automated permission to edit, merge, publish, or
deploy. A human or authorized host retains action authority.

## Reference rules

Every conclusion must:

1. include at least one `claim_refs` entry;
2. reference only Claims and Evidence present in the declared Bundle;
3. use `evidence_refs` only from the supporting Evidence of its referenced
   Claims;
4. disclose exactly all `counter_evidence_refs` declared by those Claims;
5. preserve the Bundle's `unknown` and `conflicted` boundaries.

For `accept` or `request_change`, every referenced Claim must have at least one
cited supporting or Counter-evidence record. A reviewer cannot produce a
definitive disposition while dropping the Evidence for one of its Claims.

## Acceptance boundary

`accept` has the strongest validator requirements:

- every referenced Claim has status `supported`;
- every referenced Claim has at least one cited supporting Evidence record
  with strength `corroborated` or `reproduced`;
- that Evidence has Freshness status `current`;
- no referenced Claim is `conflicted` or `unknown`.

An `observed` tool log, a stale result, or an Agent statement cannot support
acceptance by itself.

## Unknown and Conflict

If any referenced Claim is `unknown`, the only valid dispositions are
`unknown` or `request_investigation`.

A `conflicted` Claim cannot support `accept`. Its Counter-evidence must still be
listed, and the reviewer should use the limitations and unresolved questions
to state what would resolve the conflict.

Missing Evidence is not evidence that an event did not happen. A reviewer must
not strengthen `unknown` into a negative fact.

## Reasoning summary and limitations

`reasoning_summary` is a concise explanation of how the cited records support
the review conclusion. It is not an additional Evidence source.

`limitations` records the scope that the conclusion does not cover.
`next_action`, when present, is advisory and must remain within the authority
of the consuming workflow.

## Optional validation

```bash
aet bundle validate-review \
  --bundle evidence-bundle/ \
  --review review-result.json
```

A successful result reports `PASS`, the Bundle ID, conclusion count, and the
validated conclusion IDs. `PASS` means that the result obeys the implemented
reference and strength rules. It does not authenticate the reviewer, sign the
result, prove that cited source events really occurred, or certify the code.

The validator fails closed for duplicate JSON keys, non-finite numbers,
unknown fields, unknown IDs, the wrong Bundle ID, hidden Counter-evidence, and
unsupported strengthening.

## Consumer baseline

No SDK is required. A reviewer can:

1. validate or inspect `manifest.json`;
2. read `index.json` and the `core/` JSONL files;
3. produce one JSON object that matches the schema;
4. optionally ask a host with AET to validate the result.

See [Generic Agent consumption](../guides/generic-agent-consumption.md) for the
recommended reading sequence.
