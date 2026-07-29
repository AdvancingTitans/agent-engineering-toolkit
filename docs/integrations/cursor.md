# Cursor

Use AET as a local CLI beside Cursor. Project rules can point to the relevant
portable Skill instructions, while JSON output supplies the deterministic
handoff:

```bash
aet quick check . --format json
aet quick fresh --proof .aet/proofs/unit-tests.json --format json
```

AET does not assume Cursor has a built-in AET integration. Cursor's Agent makes
the engineering judgment; AET preserves evidence, scope, freshness, and
authority boundaries.
