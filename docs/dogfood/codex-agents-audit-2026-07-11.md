# Dogfood: Codex global `AGENTS.md` audit

**Scope:** only `/Users/yjw/.codex/AGENTS.md`, using a scan policy with `include = ["AGENTS.md"]`.

**Observed result:** 52 `AET-CTX-003` failures and one `AET-CTX-004` warning.

The failures were stale absolute paths in the Hermes Skill Index: the index listed folders that do not exist in the currently installed Hermes skill tree. The warning identified a 381-line / 27,044-character root instruction file, which risks always-on context bloat.

This was the real-world regression case for two v1 features: scoped inclusion prevents unrelated Codex assets from obscuring the result, and absolute local path validation makes installation drift explicit. AET intentionally did not modify the global instructions; remediation belongs to that instruction owner. A separate Trace confirmed that the environment note “No gh CLI” is also stale (`gh --version` succeeded), but command facts are retained as Trace evidence rather than inferred by the static audit.
