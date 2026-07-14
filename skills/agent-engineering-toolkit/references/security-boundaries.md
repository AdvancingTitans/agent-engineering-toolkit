# Security and runner boundaries

Raw runner output stays private; Evidence Only export excludes transcripts,
shell output, secrets and environment values. Tasks explicitly allow inherited
environment names. Runner configuration can restrict but never expand Task
permission. HOME additionally requires `inherit_home: true` for process
adapters. A runner without OS-level network isolation reports PARTIAL, and an
`enforced-deny` Task fails before execution.

Observed fixtures reject links and special files. The scorer recomputes the
workspace snapshot, validates exact structured Trace argv, declared artifacts,
logs, redaction, intent command and freshness. Command-shaped text and arbitrary
JSON are not Evidence. Host authentication/startup, missing structured events,
tampered bindings and unsupported capabilities remain INFRASTRUCTURE_ERROR,
UNKNOWN or INCONCLUSIVE, never PASS.
