# v1.18 launch checklist

## Repository-side gates

- [ ] Full deterministic suite passes.
- [ ] Installed-wheel demo passes on Ubuntu, macOS, and Windows.
- [ ] Demo JSON validates and reports `EXACT_MATCH` then
  `RELEVANT_FILES_CHANGED`.
- [ ] README is at most 250 lines and all local links pass.
- [ ] Social Preview is 1280x640, opaque, and below 1 MB.
- [ ] PyPI, runtime, tag, Release, and wheel versions agree.
- [ ] Community files and current Issue/Discussion forms exist.
- [ ] AET self-audit and self-review have no unresolved P0/P1 finding.

## Human gates

- [ ] Enable Pages and Discussions.
- [ ] Upload Social Preview and update About/Homepage/Topics.
- [ ] Publish the exact CI artifact to PyPI and GitHub Release.
- [ ] Verify public `uvx` from a clean machine.
- [ ] Create a Known limitations Discussion.
- [ ] Confirm a maintainer can respond to P0 installation issues within 24h.

No external publish, post, settings change, or outreach is automated.
