# GitHub Release brief — v1.18.0

Owner: `HUMAN_MAINTAINER`

Status: `BLOCKED_UNTIL_EXACT_ARTIFACT_PASSES`

Stop Rule: Do not publish if PyPI, runtime, tag, Release assets, or the
installed-wheel demo disagree.

## Suggested title

AET v1.18.0: Activation and Distribution

## Suggested release note — not published

AET v1.18.0 makes the existing Evidence Core easier to try and hand off. The
new installed `aet demo stale-proof` command runs a real standard-library test,
binds it to exact fixture source, verifies `EXACT_MATCH`, changes a relevant
file without rerunning the test, and reports `RELEVANT_FILES_CHANGED`.

This is an activation and distribution release. It does not change Evidence
authority, promote `UNKNOWN`, add a trust score, or grant auto-edit, merge, or
release permission.

Also included: a focused README and static site, five-Skill catalog, community
health files, a read-only GitHub Action template, and aggregate maintainer
measurement without product telemetry.

Reproduce from the exact released package:

```bash
uvx --from agent-engineering-toolkit aet demo stale-proof
```

Known limitation: Git is required for the Hero demo. This fixture is one
observed case, not a general model-quality result.
