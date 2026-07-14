# Quality workflow

`quality diagnose` is deterministic Policy lookup, not semantic RCA or an LLM
Judge. It preserves source FAIL/UNKNOWN and maps only to declared owners and
repair surfaces. `quality promote` requires a confirmed, reproducible,
de-identified badcase and writes only a validation candidate bundle. It does
not edit formal suites, production assets, tickets, prompts or releases.
