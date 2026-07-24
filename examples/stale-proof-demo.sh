#!/bin/sh
set -eu

ROOT=$(CDPATH= cd "$(dirname -- "$0")/.." && pwd)
DEMO_DIR=${TMPDIR:-/tmp}/aet-stale-proof-demo

rm -rf "$DEMO_DIR"
cp -R "$ROOT/eval/real-agent/fixtures/python-proof/repo" "$DEMO_DIR"
find "$DEMO_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +

git -C "$DEMO_DIR" init -q
printf '.aet/\n' > "$DEMO_DIR/.gitignore"
git -C "$DEMO_DIR" add .
git -C "$DEMO_DIR" -c user.name=AET -c user.email=aet@example.com commit -qm baseline

cd "$DEMO_DIR"

echo '1/3 Record a bounded Quick proof for the exact workspace'
uv run --project "$ROOT" aet quick proof \
  --artifact reports/unit-tests.txt \
  --relevant-path tests/test_add.py \
  --output .aet/proofs/unit-tests.json \
  -- python3 bin/run_proof.py

echo '2/3 Verify that the proof is fresh'
uv run --project "$ROOT" aet quick fresh \
  --proof .aet/proofs/unit-tests.json \
  --format json > .aet/proofs/fresh.json
python3 -c 'import json; d=json.load(open(".aet/proofs/fresh.json")); print("freshness:", d["freshness_state"]); assert d["freshness_state"] == "EXACT_MATCH"'

echo '3/3 Change the workspace without rerunning the proof'
python3 -c 'from pathlib import Path; p=Path("tests/test_add.py"); p.write_text(p.read_text().replace("1 + 1, 2", "1 + 1, 3"))'
if uv run --project "$ROOT" aet quick fresh \
  --proof .aet/proofs/unit-tests.json \
  --format json > .aet/proofs/stale.json
then
  echo 'Expected stale proof to return a non-zero status' >&2
  exit 1
fi
python3 -c 'import json; d=json.load(open(".aet/proofs/stale.json")); print("freshness:", d["freshness_state"]); assert d["freshness_state"] == "RELEVANT_FILES_CHANGED"'

echo "Demo passed. Inspect $DEMO_DIR/.aet/proofs/ for the compact proof and freshness results."
