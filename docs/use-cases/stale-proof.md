# Stale proof

A test log answers a historical question: what happened when this command ran?
It does not automatically answer whether the result still applies after the
workspace changes.

## Reproduce

```bash
aet demo stale-proof
```

The installed fixture contains one correct `add` implementation and one
standard-library test. AET:

1. initializes a temporary Git repository;
2. runs `python -m unittest discover -s tests` through `quick_proof`;
3. binds `src/calc.py` and `tests/test_calc.py`;
4. confirms `EXACT_MATCH`;
5. changes addition to subtraction without rerunning the test;
6. calls `quick_fresh` and observes `RELEVANT_FILES_CHANGED`.

The proof lives outside the Git workspace, so writing it cannot make itself
stale. The fixture and mutation are hash checked. No second freshness
implementation exists inside the demo.

## Interpretation

`RELEVANT_FILES_CHANGED` does not mean the earlier command failed. It means the
earlier successful execution is no longer evidence about the current content
of a declared relevant file.

The demo does not establish full-suite coverage, model quality, merge safety,
or correctness outside this one fixture. Missing Git, corrupt resources,
timeouts, and path violations fail closed.
