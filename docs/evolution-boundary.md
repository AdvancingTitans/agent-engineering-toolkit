# Evidence-Gated Evolution Boundary

`aet learn` improves routing guidance from structured local evidence. It is not
an autonomous self-modifying Agent.

## Immutable contract

The following never enter the optimizer's edit budget:

- `UNKNOWN` is never a pass.
- Only `aet trace -- <argv>` executes a declared command.
- `audit`, `review`, and Evidence Pack compilation do not execute proof commands.
- A context `--read` record is an attestation, not proof of model comprehension.
- A proposal, replay, gate, or stage is not adoption.
- Candidate adoption, Git commit, Git push, and remote sharing require explicit human action.

The canonical Skill wraps immutable text in `aet-learn:immutable` markers.
Candidates can change only named `aet-learn:editable` blocks. Gate 0 compares
the immutable bytes, target type, operation count, and edit budget before any
evaluation runs.

## Evidence and privacy

The default **Evidence Only** profile reads AET JSON reports, finding IDs,
statuses, command/artifact hashes, snapshots, and explicit rejection reasons.
It does not read transcripts, shell output, environment variables, or secrets.
`harvest` is local and accepts multiple evidence directories, including a
user-maintained `~/.aet/experience/` collection; it never uploads or fetches
experience data.

## Gate policy

Every candidate must pass all of these:

1. bounded Patch IR and immutable-contract checks;
2. static candidate self-audit in a temporary copy;
3. immutable core evaluation with no regression;
4. separate validation and held-out suites with no regression and at least one improvement;
5. explicit human review before adoption.

The result is a metric vector, not an Agent trust score. Rejected candidates
remain auditable input for future human or model-assisted proposals.

## Model adapters

`--engine model` is opt-in and requires an explicit `--model-command` argv.
The adapter receives a JSON request on stdin and must return bounded Patch IR
JSON on stdout. Its output cannot modify evidence, decide a Gate, or adopt a
candidate. Rule proposals remain the default.
