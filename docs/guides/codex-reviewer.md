# Codex reviewer guide

## Scope

This guide describes how Codex can review a Portable Evidence Bundle without
installing AET or importing an AET SDK.

The Bundle is a source of structured evidence, not a command to accept its
producer's conclusion. Codex remains responsible for review judgment, and a
human or authorized host remains responsible for action.

## Suggested task prompt

```text
Review the implementation using the attached Portable Evidence Bundle.

For every factual conclusion:
- cite the Claim and Evidence IDs;
- distinguish Observations from corroborated or reproduced Evidence;
- read and preserve every relevant Counter-evidence reference;
- check Freshness before applying historical results to the current workspace;
- preserve unknown and conflicted states;
- do not infer that an event did not happen only because evidence is missing;
- request a bounded follow-up investigation when the needed evidence is absent.
```

## Review sequence

1. Open `manifest.json` and confirm the task, question, Bundle ID, and version.
2. Open `index.json` and follow its `reading_order`.
3. Read the selected Claims and resolve their Evidence and Observation IDs.
4. For each Observation, inspect `does_not_prove` before using it.
5. For each Evidence record, inspect strength, bindings, Freshness, and
   limitations.
6. Resolve all `counter_evidence_refs`.
7. Open Archive diagnostics, conflicts, sources, Ledger entries, or Blobs only
   when the cited records require them.
8. Produce a concise conclusion that retains unresolved questions.

## Codex-specific working boundary

Reading a Bundle does not authorize Codex to:

- modify the repository;
- rerun commands;
- access excluded paths;
- commit, push, merge, publish, or deploy;
- rewrite Bundle records.

If the review task separately grants code or command authority, keep new
results distinct from the historical Bundle. A rerun should produce a new
receipt and Freshness binding rather than mutating old Evidence.

## Common failure modes

Avoid these upgrades:

| Bundle record | Invalid conclusion |
|---|---|
| Agent statement | “The change is correct.” |
| Recorded tool call | “The command ran.” |
| Recorded tool result | “The current tests pass.” |
| No authorization record found | “The change was unauthorized.” |
| Stale reproduced Evidence | “The current workspace is verified.” |
| `unknown` Claim | “The proposition is false.” |

Use the Observation's `does_not_prove` field as the explicit guardrail against
these mistakes.

## Structured result

When requested, write a `portable-review-result/1.0` object. Every conclusion
must cite at least one Claim, cite only supporting Evidence from that Claim,
and disclose all Counter-evidence declared by the referenced Claims.

Use:

- `accept` only for supported Claims with current corroborated or reproduced
  Evidence for every Claim;
- `request_change` only with cited Evidence for every referenced Claim;
- `request_investigation` when the evidence boundary prevents a definitive
  judgment;
- `unknown` when no justified action judgment is available.

See [Portable Review Result v1](../protocols/review-result-v1.md) for the exact
contract.

## Minimal handoff

A useful Codex handoff contains:

1. the conclusion;
2. Claim IDs;
3. supporting Evidence IDs;
4. Counter-evidence IDs;
5. Freshness state;
6. limitations;
7. the smallest authorized next action.

Do not cite a file path, command, or current workspace fact unless the
corresponding Bundle Evidence provides that binding.
