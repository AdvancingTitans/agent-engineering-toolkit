# Start here

## 1. See stale proof in under 90 seconds

Run the exact v1.19.1 GitHub Release wheel:

```bash
uvx --from https://github.com/AdvancingTitans/agent-engineering-toolkit/releases/download/v1.19.1/agent_engineering_toolkit-1.19.1-py3-none-any.whl aet demo stale-proof
```

The expected transition is:

```text
test executes: PASS
before mutation: EXACT_MATCH
after relevant source mutation: RELEVANT_FILES_CHANGED
demo result: PASS
```

The final `PASS` means AET detected the expected stale state. It does not mean
the mutated source passed the test.

## 2. Pick one question

- Instructions or Skills look risky: `aet quick check .`
- A diff may exceed the task: `aet quick scope . --base main --intent aet.intent.json`
- A command must run now: `aet quick proof ... -- <argv>`
- Existing proof may be stale: `aet quick fresh --proof <proof.json>`
- You need a read-only implementation plan: `/aet-plan`
- You need bounded graph-first review context: `aet review-graph open ...`
- You need evidence-grounded behavioural diagnosis: `aet risk diagnose ...`

Do not chain every surface automatically. Each Quick command answers one
bounded question and stops.

## 3. Try proof on your repository

```bash
aet quick proof \
  --output .aet/proofs/unit-tests.json \
  --relevant-path src/app.py \
  --relevant-path tests/test_app.py \
  -- python -m unittest discover -s tests

aet quick fresh --proof .aet/proofs/unit-tests.json --format json
```

Declare only files the command genuinely covers. AET will not infer complete
test coverage from a successful exit code.

## 4. Read the boundary that matters

- [Status and authority](reference/status-and-authority.md)
- [AET vs CI](comparisons/aet-vs-ci.md)
- [Portable cross-Agent handoff](use-cases/cross-agent-handoff.md)
- [Complete technical overview](reference/full-product-overview.md)
