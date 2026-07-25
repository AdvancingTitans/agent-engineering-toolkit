# Claude Code reviewer guide

## Scope

Claude Code can consume a Portable Evidence Bundle directly from its directory
files. No AET installation or dedicated SDK is required for review.

The review must keep Run Record Observations separate from Verified Evidence.
The Bundle does not delegate code-editing, command-execution, Git, or release
authority.

## Suggested task prompt

```text
Use the Portable Evidence Bundle as a structured source, not as final authority.

Read manifest.json and index.json first. For each conclusion, cite Claim and
Evidence IDs, disclose Counter-evidence, check Freshness, and preserve unknown
or conflicted states. An Observation proves only its `proves` statements and
does not prove anything listed in `does_not_prove`. Do not treat missing
evidence as evidence that an event did not occur.
```

## File-reading strategy

Start with:

```text
manifest.json
index.json
core/claims.jsonl
core/evidence.jsonl
core/observations.jsonl
```

Read only the Archive records and Blobs referenced by the Claims being
reviewed. This keeps context bounded while preserving traceability.

Open Archive when:

- a Claim is `conflicted`;
- a diagnostic affects a cited Observation or Evidence record;
- Freshness is stale or `unknown`;
- identity is `content`;
- a model-facing result is truncated;
- the Ledger is needed to understand the disconfirming search.

## Evidence rules

- Agent prose is `context_only`.
- A recorded tool call or result is at most `observed` without independent
  verification.
- `corroborated` Evidence has independent support but still requires its
  declared binding and Freshness.
- `reproduced` Evidence was rerun under the declared current binding.
- Multiple weak records do not combine into reproduced proof.

Do not quote a reasoning record as factual evidence. Reasoning is excluded from
public export by default and, when visible within a private normalized run,
serves only as hypothesis context.

## Command and edit boundary

Reviewing the Bundle is read-only. Do not run tests, edit files, or change Git
state unless the surrounding user request independently authorizes those
actions.

When a rerun is authorized:

1. state that it is new evidence, not part of the historical Bundle;
2. bind argv, working directory, exit status, relevant paths, and environment;
3. check Freshness after later changes;
4. retain the old record rather than overwriting it.

## Review output

For a prose review, include:

- conclusion;
- cited Claim and Evidence IDs;
- Counter-evidence;
- Freshness;
- unresolved limitations;
- smallest next action.

For a machine-checkable review, use
`portable-review-result/1.0`. `accept` requires a supported Claim and current
corroborated or reproduced Evidence for every cited Claim. `unknown` Claims
must remain `unknown` or request further investigation.

See [Generic Agent consumption](generic-agent-consumption.md) and
[Portable Review Result v1](../protocols/review-result-v1.md).
