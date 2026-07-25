---
name: aet-investigate
description: Create a bounded, read-only investigation from normalized Codex or Claude Code Run Records, optionally inspect explicit AET Proof and Freshness records, and export a Portable Evidence Bundle for an independent reviewer.
---

# /aet-investigate

Answer one declared investigation question with a portable evidence handoff.

## Boundary

- Keep the target workspace read-only.
- Do not execute arbitrary commands, modify code, commit, push, merge, publish, or repair.
- Require one primary hypothesis, at least one competing hypothesis, and a
  disconfirming search.
- Treat Run Records as historical behavior. They may create Observations and
  Evidence Candidates, but only explicit `proof.inspect` and `freshness.check`
  results may create Verified Evidence.
- Preserve `unknown`, counter-evidence, diagnostics, Freshness limitations, and
  every `does_not_prove` statement.
- Use `policy.json` and `tool-contract.json` without expanding their authority.

## Workflow

1. Normalize one declared run when a normalized directory is not already
   available:

   ```bash
   aet run normalize --source <codex|claude-code> \
     --input <session.jsonl> --output <normalized-run>
   ```

2. Create an `investigation-request/1.0` JSON object. Bind its `run_sources`
   entry to the normalized Manifest's `source_type` and `run_group_id`. Copy the
   budgets and privacy boundary from `policy.json`; narrow them when possible.

3. Run the investigator. Without a Proof it remains observation-only:

   ```bash
   aet investigate --request <request.json> \
     --run <normalized-run> --output <investigation.json>
   ```

   To inspect an existing deterministic Proof, the Policy must allow
   `proof.inspect` and `freshness.check`, and their budgets must be non-zero:

   ```bash
   aet investigate --request <request.json> \
     --run <normalized-run> --workspace <workspace> \
     --proof <proof.json> --output <investigation.json>
   ```

   The Proof path and its recorded workspace must remain inside and match the
   declared read-only workspace. A matching recorded command Candidate may be
   marked `verified`; stale Proof remains historical Evidence and cannot answer
   a current-workspace Claim.

4. Compile and validate the handoff:

   ```bash
   aet bundle create --investigation <investigation.json> \
     --output <evidence-bundle>
   aet bundle validate <evidence-bundle>
   ```

5. Return only the bounded status, unresolved questions, Bundle path, and the
   smallest authorized next action. A reviewer does not need AET installed to
   read `manifest.json`, `index.json`, `core/*.jsonl`, and `report.md`.

## Completion check

Claim completion only when `aet bundle validate <evidence-bundle>` returns
`PASS`. Confirm the Investigation preserves the original Policy and Ledger,
does not promote Agent self-report, and exports real Run Group, Record identity,
Proof, Freshness, Source type, and Content Hash bindings. A non-`unknown`
finding requires current deterministic Evidence.

Stop after the validated Bundle. Do not continue into repair, new command
execution, Learn, Stage, Adopt, or release work.
