# Security and retention

- `audit`, `review`, `triage`, and local `evolve` are read-only.
- `trace` is the only generic command executor. It requires `--`, records the
  explicit argv, and writes redacted logs plus digests. `--artifact` is a
  separate explicit opt-in for one workspace-relative UTF-8 text report; the
  report is redacted before it enters Trace or an Evidence Pack. stdout and
  stderr remain excerpt-and-digest only.
- Artifact paths may not be absolute or resolve outside the workspace. Missing,
  non-regular, undecodable, and unredactable artifacts remain `UNKNOWN` and
  make an otherwise successful Trace invocation return non-zero.
- `evolve --remote github` is opt-in and records endpoint, retrieval time,
  status, and payload hash in its source manifest. No network access occurs by
  default.
- AET does not upload repository data or collect telemetry.
- Evidence artifacts may contain paths, commit subjects, and redacted command
  excerpts. Keep `.aet/` private unless its content has been reviewed.
- Real-host Skill replay provides isolated workspace copies, not a claim of
  OS-level sandboxing. Network isolation and command enforcement remain
  `PARTIAL` unless an external sandbox supplies and records those controls.
- Shadow Audit artifacts can reveal candidate findings and repository
  fingerprints. Keep them private until reviewed; Shadow never changes the
  official report or exit code.
- Candidate manifests, Gate reports, confirmations, and Decision Ledgers are
  durable governance evidence. Retain them with the adopted asset; rejected
  candidates may be retained locally as negative constraints or deleted under
  the repository's normal retention policy.
