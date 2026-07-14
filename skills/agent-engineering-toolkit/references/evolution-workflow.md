# Evidence-gated evolution workflow

Run only when the user explicitly requests governance-asset evolution.

```bash
aet learn harvest --evidence .aet/evidence --output .aet/learn/experiences.json
aet learn inspect --experiences .aet/learn/experiences.json --output .aet/learn/inspection.json
aet learn mine --experiences .aet/learn/experiences.json --output .aet/learn/patterns.json
aet learn propose --patterns .aet/learn/patterns.json --target <asset> --output <candidate>

aet learn plan --candidate <candidate> --core <core> --validation <validation> \
  --held-out <held-out> --runner codex --runner-config <runner.json> \
  --risk-class R3 --claim <claim-id> --output <gate-plan.json>
aet learn gate --candidate <candidate> --core <core> --validation <validation> \
  --held-out <held-out> --runner codex --runner-config <runner.json> \
  --gate-plan <gate-plan.json> --output <gate.json>
```

The Plan binds Candidate, Runner, configuration, Scorer, Tasks and Fixtures.
Core is a contract-retention check; Validation and Held-out use a predeclared
directional paired objective. Sequential looks spend a fixed family alpha;
ordinary fixed-sample p-values may not be repeatedly peeked. Historical records
may inform planning assumptions only; fresh pairs alone decide PASS. Held-out
opens only after preceding objectives pass. Infrastructure errors and
INCONCLUSIVE never stage. `stage` is not Adoption; `adopt --yes` remains an
explicit human write.
