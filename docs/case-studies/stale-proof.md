# Case study: the tests passed, but the proof was stale

A coding Agent reports that the tests passed. A few minutes later the workspace
changes, but the old green log remains. The command really succeeded; it just no
longer proves the current code.

This 60-second local demo records a test run, verifies the exact workspace, then
changes the test without rerunning it:

```bash
./examples/stale-proof-demo.sh
```

The important transition is deliberately small:

```text
1/3 Record proof for the exact workspace
2/3 Verify that the proof is fresh
freshness: EXACT_MATCH
3/3 Change the workspace without rerunning the proof
freshness: HEAD_MATCH_WORKTREE_DIFFERS
```

The second receipt does not rewrite the historical execution result. The command
still exited successfully, while current-workspace freshness becomes `FAIL`.
That separation prevents two common mistakes:

- treating an old passing log as proof for new bytes;
- pretending the command itself failed when the real problem is stale evidence.

The demo is deterministic, uses only a temporary Git repository, and leaves its
JSON evidence under `${TMPDIR:-/tmp}/aet-stale-proof-demo/.aet/evidence/` for
inspection. It does not call a model or a network service.

## Reproduce manually

The fixture declares `unit-tests` in `aet.intent.json`. AET binds the exact
command, artifact, intent and workspace snapshot:

```bash
aet trace --proof unit-tests --intent aet.intent.json \
  --artifact reports/unit-tests.txt \
  --output .aet/evidence/trace.json \
  -- python3 bin/run_proof.py

aet evidence receipt --report .aet/evidence/trace.json
```

After any tracked or untracked workspace change, run the receipt command again.
No test command is executed during receipt generation.
