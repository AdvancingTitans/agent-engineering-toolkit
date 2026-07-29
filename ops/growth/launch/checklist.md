# v1.18 launch checklist

## Repository-side gates

- [x] Full deterministic suite passes.
- [x] Installed-wheel demo passes on Ubuntu, macOS, and Windows.
- [x] Demo JSON validates and reports `EXACT_MATCH` then
  `RELEVANT_FILES_CHANGED`.
- [x] README is at most 250 lines and all local links pass.
- [x] Social Preview is 1280x640, opaque, and below 1 MB.
- [x] PyPI, runtime, tag, Release, and wheel versions agree.
- [x] Community files and current Issue/Discussion forms exist.
- [x] AET self-audit and self-review have no unresolved P0/P1 finding.

## Human gates

- [x] Enable Pages and Discussions.
- [x] Upload Social Preview and update About/Homepage/Topics.
- [x] Publish the exact CI artifact to PyPI and GitHub Release.
- [x] Verify public `uvx` from a clean machine.
- [x] Create a Known limitations Discussion.
- [ ] Confirm a maintainer can respond to P0 installation issues within 24h.

Completed settings and publication gates were performed through the
authenticated GitHub UI; no workflow auto-posts or performs outreach.
