# Provenance workflow

Use `context discover/record/verify` to bind available local assets; `--read` is
an attestation, not proof that a model understood or used them. Use `decision
init/add/verify` for source-backed decisions. Use `evolve plan/collect/build/report`
for repository archaeology, and add `--remote github` only when explicitly
requested. Missing remote evidence remains UNKNOWN; textual Issue/PR references
are candidates until source objects establish them.
