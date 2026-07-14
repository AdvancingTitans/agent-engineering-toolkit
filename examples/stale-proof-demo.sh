#!/bin/sh
set -eu

ROOT=$(CDPATH= cd "$(dirname -- "$0")/.." && pwd)
DEMO_DIR=${TMPDIR:-/tmp}/aet-stale-proof-demo

rm -rf "$DEMO_DIR"
cp -R "$ROOT/eval/real-agent/fixtures/python-proof/repo" "$DEMO_DIR"
find "$DEMO_DIR" -type d -name __pycache__ -prune -exec rm -rf {} +

git -C "$DEMO_DIR" init -q
git -C "$DEMO_DIR" add .
git -C "$DEMO_DIR" -c user.name=AET -c user.email=aet@example.com commit -qm baseline

cd "$DEMO_DIR"

echo '1/3 Record proof for the exact workspace'
uv run --project "$ROOT" aet trace \
  --proof unit-tests \
  --intent aet.intent.json \
  --artifact reports/unit-tests.txt \
  --output .aet/evidence/trace.json \
  -- python3 bin/run_proof.py

echo '2/3 Verify that the proof is fresh'
uv run --project "$ROOT" aet evidence receipt \
  --report .aet/evidence/trace.json \
  --output .aet/evidence/fresh.json
python3 -c 'import json; d=json.load(open(".aet/evidence/fresh.json")); print("freshness:", d["freshness"]["state"]); assert d["freshness"]["status"] == "PASS"'

echo '3/3 Change the workspace without rerunning the proof'
python3 -c 'from pathlib import Path; p=Path("tests/test_add.py"); p.write_text(p.read_text().replace("1 + 1, 2", "1 + 1, 3"))'
uv run --project "$ROOT" aet evidence receipt \
  --report .aet/evidence/trace.json \
  --output .aet/evidence/stale.json
python3 -c 'import json; d=json.load(open(".aet/evidence/stale.json")); print("freshness:", d["freshness"]["state"]); assert d["freshness"]["status"] == "FAIL"'

echo "Demo passed. Inspect $DEMO_DIR/.aet/evidence/ for the complete evidence."
