# Case study: the tests passed, but the proof was stale

A coding Agent reports that the tests passed. A few minutes later the workspace
changes, but the old green log remains. The command really succeeded; it just no
longer proves the current code.

This local Quick demo records a bounded test run, verifies the exact workspace, then
changes the test without rerunning it:

```bash
./examples/stale-proof-demo.sh
```

The important transition is deliberately small:

```text
1/3 Record a bounded Quick proof for the exact workspace
2/3 Verify that the proof is fresh
freshness: EXACT_MATCH
3/3 Change the workspace without rerunning the proof
freshness: RELEVANT_FILES_CHANGED
```

The freshness result does not rewrite the historical execution result. The command
still exited successfully, while current-workspace freshness becomes `FAIL`.
That separation prevents two common mistakes:

- treating an old passing log as proof for new bytes;
- pretending the command itself failed when the real problem is stale evidence.

The demo is deterministic, uses only a temporary Git repository, and leaves its
JSON evidence under `${TMPDIR:-/tmp}/aet-stale-proof-demo/.aet/proofs/` for
inspection. It does not call a model or a network service.

## Reproduce manually

The Quick proof binds the exact command, relevant test path, artifact, environment
and workspace snapshot:

```bash
aet quick proof \
  --relevant-path tests/test_add.py \
  --artifact reports/unit-tests.txt \
  --output .aet/proofs/unit-tests.json \
  -- python3 bin/run_proof.py

aet quick fresh --proof .aet/proofs/unit-tests.json
```

After a relevant file, declared artifact, environment binding or workspace baseline
changes, run `aet quick fresh` again. It does not execute the test command.
