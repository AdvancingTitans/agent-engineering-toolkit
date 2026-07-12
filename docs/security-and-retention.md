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
