---
name: release-check
description: Verify a release candidate before publishing it.
---

# Release check

Run `python scripts/check_release.py` and inspect the exit status before saying
that the release is ready. Generated evidence is named `evidence_YYYYMMDD.json`.
See [the detailed procedure](references/checks.md).
