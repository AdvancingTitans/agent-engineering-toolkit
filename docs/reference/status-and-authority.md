# Status and authority

## Evidence statuses

| Status | Meaning |
| --- | --- |
| `PASS` | The bounded check's stated conditions were satisfied. |
| `FAIL` | A stated condition was contradicted or execution failed. |
| `UNKNOWN` | Required evidence is missing, unreadable, ambiguous, or unavailable. |
| `NOT_APPLICABLE` | The check does not apply to this target. |

Never collapse these into a holistic trust score.

## Freshness states

`EXACT_MATCH` means the recorded workspace snapshot still matches.
`RELEVANT_FILES_MATCH` and `HEAD_CHANGED_RELEVANT_FILES_MATCH` preserve the
declared relevant-file binding while reporting broader workspace changes.
`RELEVANT_FILES_CHANGED`, `ARTIFACT_CHANGED`, and `ENVIRONMENT_CHANGED` mean
the historical result no longer has current applicability under that binding.
Unreadable or incomplete proof remains `UNKNOWN`.

## Authority layers

- An **Observation** records what a source or Agent run contains.
- An **Evidence Candidate** identifies a proposition worth verification.
- **Verified Evidence** requires an authorized deterministic binding.
- A portable **Claim** retains evidence, counter-evidence, and limitations.
- An Improvement or Plan remains advice or `PROPOSED`, not Evidence.
- A human or external release process decides whether to edit, merge, deploy,
  or publish.

AET never auto-adopts, commits, pushes, merges, releases, or upgrades missing
authority for presentation.
