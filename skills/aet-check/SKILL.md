---
name: aet-check
description: Run a bounded AET check of Agent instructions, Skills, verification contracts, and dangerous authority. Use only when the user explicitly invokes /aet-check or asks for this AET Quick check.
---

# /aet-check

Answer one question: are this repository's Agent engineering assets usable and
honest about verification?

## Boundary

- Start with `aet quick check <root> --format json`.
- Read only Agent instructions, Skills, README, package/test configuration, CI,
  and files directly relevant to the finding.
- Do not read complete Git history, execute project code, access credentials,
  write files, or call remote tools by default.
- The deterministic preflight owns `PASS`, `FAIL`, `UNKNOWN`, and
  `NOT_APPLICABLE`. Never rewrite them.

## Investigation

The host LLM may form at most three competing hypotheses and use authorized
tools to clarify project-specific meaning. Every factual claim needs a
hash-bound `result_ref`; inspect a reasonable counter-explanation before
issuing `SUPPORTED`. Preserve the distinction between facts, engineering
judgment, uncertainty, and suggested action.

Before rendering an Investigated Finding, pass the canonical Finding, Ledger,
authorized-tool set, and Investigation Contract through
`aet.investigation.validate_investigated_finding`. If that API is unavailable
or rejects the record, preserve `HYPOTHESIS`/`UNKNOWN` and disclose why.

Budget: 30 seconds, three rounds, at most two LLM calls, six tool calls, one
expensive call, zero remote calls, and five reported findings.

If the user invoked `/aet-check` in Chinese and asked in Chinese, explain the
result in natural Simplified Chinese while keeping code and required technical
terms in English. Otherwise use English.

Emit the bounded report, disclose uninspected surfaces, and stop. Do not start
Scope, Proof, Fresh, Learn, Gate, Stage, Adopt, or a repair.
