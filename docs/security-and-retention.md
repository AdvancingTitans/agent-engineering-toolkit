# Security and retention

- `audit`, `review`, `triage`, and local `evolve` are read-only.
- `trace` is the only generic command executor. It requires `--`, records the
  explicit argv, and writes redacted logs plus digests.
- `evolve --remote github` is opt-in and records endpoint, retrieval time,
  status, and payload hash in its source manifest. No network access occurs by
  default.
- AET does not upload repository data or collect telemetry.
- Evidence artifacts may contain paths, commit subjects, and redacted command
  excerpts. Keep `.aet/` private unless its content has been reviewed.
