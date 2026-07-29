#!/usr/bin/env bash
set -euo pipefail

: "${MODE:?MODE is required}"
: "${GITHUB_WORKSPACE:?GITHUB_WORKSPACE is required}"
: "${GITHUB_OUTPUT:?GITHUB_OUTPUT is required}"

PATH_INPUT=${PATH_INPUT:-.}
FORMAT=${FORMAT:-json}
OUTPUT=${OUTPUT:-.aet/aet-action-result.json}
AET_BIN=${AET_BIN:-aet}
PYTHON_BIN=${PYTHON_BIN:-python3}

case "$FORMAT" in
  json|markdown) ;;
  *) echo "unsupported format: $FORMAT" >&2; exit 64 ;;
esac

case "$OUTPUT" in
  /*|../*|*/../*|*/..|..)
    echo "output must stay inside GITHUB_WORKSPACE" >&2
    exit 64
    ;;
esac

cd "$GITHUB_WORKSPACE"
mkdir -p "$(dirname "$OUTPUT")"
temporary="${OUTPUT}.tmp"

case "$MODE" in
  check)
    argv=("$AET_BIN" quick check "$PATH_INPUT" --format "$FORMAT")
    ;;
  scope)
    : "${BASE:?BASE is required for scope}"
    : "${INTENT:?INTENT is required for scope}"
    argv=("$AET_BIN" quick scope "$PATH_INPUT" --base "$BASE" --intent "$INTENT" --format "$FORMAT")
    ;;
  fresh)
    : "${PROOF:?PROOF is required for fresh}"
    argv=("$AET_BIN" quick fresh --proof "$PROOF" --format "$FORMAT")
    ;;
  proof)
    echo "mode=proof is intentionally unsupported; run explicit AET CLI in a trusted workflow" >&2
    exit 64
    ;;
  *)
    echo "unsupported mode: $MODE" >&2
    exit 64
    ;;
esac

set +e
"${argv[@]}" >"$temporary"
status=$?
set -e
mv "$temporary" "$OUTPUT"

authoritative_status=UNKNOWN
freshness_state=
if [ "$FORMAT" = json ]; then
  values=$("$PYTHON_BIN" - "$OUTPUT" <<'PY'
import json, sys
value=json.load(open(sys.argv[1], encoding="utf-8"))
summary=value.get("summary", {})
status=value.get("authoritative_status")
if not status:
    status="FAIL" if summary.get("FAIL", 0) else "UNKNOWN" if summary.get("UNKNOWN", 0) else "PASS"
print(status)
print(value.get("freshness_state", ""))
PY
)
  authoritative_status=$(printf '%s\n' "$values" | sed -n '1p')
  freshness_state=$(printf '%s\n' "$values" | sed -n '2p')
fi

{
  printf 'authoritative-status=%s\n' "$authoritative_status"
  printf 'freshness-state=%s\n' "$freshness_state"
  printf 'report-path=%s\n' "$OUTPUT"
} >>"$GITHUB_OUTPUT"

exit "$status"
