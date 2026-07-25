# Portable Evidence Bundle threat model

## Security objective

Portable Evidence Bundle v1 is designed to detect unauthorized content
mutation, prevent unsafe local file traversal during loading, preserve evidence
strength and Counter-evidence, and reduce accidental secret export.

It is not a source-authentication, signing, sandboxing, or remote attestation
protocol.

## Protected assets

- Bundle file and Blob bytes
- Claim, Evidence, Observation, Source, Conflict, Diagnostic, and Ledger
  references
- task, workspace, Commit, command, path, and environment bindings
- Counter-evidence and `unknown` states
- investigation policy and budgets
- secret-bearing native text and tool output

## Trust boundaries

The following inputs are untrusted until validated:

- native Agent run exports;
- normalized Run Record directories received from another process;
- investigation requests and results;
- complete Bundle compiler payloads;
- Bundle directories;
- Portable Review Result JSON;
- Blob contents and file paths.

The Bundle producer, native Agent runtime, and reviewer are separate actors.
Possession of a valid Bundle does not establish that any one of them is
trustworthy.

## Integrity is not authenticity

The Manifest records SHA-256 for every declared file. Content-addressed Blobs
use the same digest in their path. The Bundle content hash binds the canonical
Manifest with its own hash field zeroed for calculation.

These checks detect mutation relative to the sealed Manifest. They do not:

- identify or authenticate the producer;
- prove that the native run came from the claimed host;
- prove that a tool or command executed;
- prove that captured output is complete or truthful;
- prove authorization;
- establish current Freshness without the declared comparison;
- provide non-repudiation.

Portable Evidence Bundle v1 does not define digital signatures, certificates,
keys, transparency logs, or a trust root. A distribution system that requires
producer authentication must add and govern that layer separately without
reinterpreting the v1 integrity fields.

## Threats and implemented controls

### Path traversal and link substitution

Threat: a Manifest path escapes the Bundle root, or a symbolic link redirects a
read to external content.

Controls:

- paths must be normalized, relative POSIX paths;
- absolute paths, `..`, backslashes, NUL bytes, and duplicate content paths are
  rejected;
- the Bundle root and every traversed entry must not be a symbolic link;
- special files are rejected;
- each resolved file must remain inside the root.

### File or Blob mutation

Threat: an attacker edits, deletes, substitutes, or injects evidence material.

Controls:

- every declared file has a SHA-256;
- Blob filenames must match their bytes;
- Evidence and Source Blob references must resolve;
- unexpected tree entries and invalid reference closure fail validation;
- truncated Evidence requires a complete Blob reference and original byte
  count.

### Reference smuggling

Threat: a Claim cites nonexistent support, a review cites unrelated Evidence,
or an Evidence record silently changes the Claim relationship.

Controls:

- IDs are unique by record class;
- all cross-references must resolve;
- Evidence `supports` and `contradicts` relationships are checked against
  Claims;
- Review Result Evidence must belong to the referenced Claims;
- definitive dispositions require cited Evidence for every referenced Claim.

### Counter-evidence suppression

Threat: a producer or reviewer hides contradictory material.

Controls:

- Claim Counter-evidence and Evidence `contradicts` relations must be
  bidirectionally complete;
- a `conflicted` Claim requires Counter-evidence and a covering unresolved
  Conflict record;
- a Portable Review Result must disclose exactly the Counter-evidence declared
  by its referenced Claims.

These controls can detect omission from a declared Bundle. They cannot discover
Counter-evidence that the investigation never collected.

### Evidence-strength escalation

Threat: an Agent statement or historical tool log is presented as current
reproduced proof.

Controls:

- Observation and Evidence are separate files and schemas;
- every Observation requires non-empty `proves` and `does_not_prove`;
- Evidence strength is discrete;
- `accept` requires current corroborated or reproduced Evidence for every
  referenced Claim;
- stale, conflicted, and unknown states block unsupported acceptance.

### Resource exhaustion

Threat: a Bundle contains very large Blobs or an excessive declared read.

Controls:

- the policy declares `max_blob_bytes_read`;
- the loader uses the lower of the caller limit and Bundle policy limit;
- investigation policy has separate record, candidate, verified-evidence, and
  tool-call budgets;
- Index/Core/Archive selection supports bounded default consumption.

JSONL record count and ordinary text file size are not a substitute for host
resource limits. Untrusted Bundle processing should still run with normal
process memory and time limits.

### Secret disclosure

Threat: native messages, tool output, paths, or Blobs expose credentials.

Controls:

- reasoning export is policy controlled and disabled in canonical records for
  public export;
- deterministic redaction covers recognized credential patterns;
- diagnostics do not echo native content;
- redacted Blob bytes receive new content addresses;
- stable reference fields fail closed when redaction would mutate identity;
- non-UTF-8 Blobs fail closed when secret redaction is required.

Pattern redaction cannot guarantee discovery of every secret format. A human or
host policy review is still required before public distribution.

### Command or workspace mutation

Threat: a portable investigation uses review authority to modify code or Git
state.

Controls:

- the current portable investigator requires `read_only: true`;
- write-like tools are rejected;
- command execution and command prefixes must be disabled;
- results remain `unknown` and contain no Verified Evidence;
- output creation refuses to overwrite an existing investigation or Bundle.

A later, separately authorized deterministic verifier must record its own
command and workspace evidence. The read-only ingestion runtime does not grant
that authority.

## Residual risks

- A malicious producer can create a self-consistent but false Bundle.
- A compromised native runtime can fabricate run records.
- Uncollected Counter-evidence cannot be validated.
- Hash collisions are treated according to SHA-256's standard security
  assumptions.
- Redaction patterns may miss novel credential formats.
- A reviewer may ignore protocol guidance unless a host validates the
  structured Review Result.
- A valid historical Bundle can still be irrelevant to a changed workspace.
- The protocol does not provide OS-level sandboxing.

## Safe handling checklist

- [ ] Validate the Bundle before consuming it.
- [ ] Keep native and normalized runs private by default.
- [ ] Apply secret redaction before export.
- [ ] Respect both host and Bundle Blob budgets.
- [ ] Do not execute Bundle content or Blobs.
- [ ] Inspect Counter-evidence, diagnostics, and Freshness.
- [ ] Preserve historical Evidence; create a new investigation for new facts.
- [ ] Add external producer authentication when the distribution threat model
      requires it.
