#!/usr/bin/env bash
set -euo pipefail

template_root=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
test_root=$(mktemp -d)
trap 'rm -rf "$test_root"' EXIT
workspace="$test_root/work space"
mkdir -p "$workspace"
printf '# Fixture\n' >"$workspace/README.md"
git -C "$workspace" init -q
git -C "$workspace" -c user.name=AET -c user.email=aet@example.invalid add .
git -C "$workspace" -c user.name=AET -c user.email=aet@example.invalid commit -qm baseline

stub="$test_root/aet"
cat >"$stub" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$@" >"$ARG_LOG"
printf '{"authoritative_status":"PASS","freshness_state":"EXACT_MATCH"}\n'
SH
chmod +x "$stub"

export AET_BIN="$stub"
export ARG_LOG="$test_root/argv.txt"
export GITHUB_WORKSPACE="$workspace"
export GITHUB_OUTPUT="$test_root/github-output.txt"
export FORMAT=json
export OUTPUT='.aet/result.json'

MODE=check PATH_INPUT='path with spaces;$(touch injected)' \
  "$template_root/run.sh"
test ! -e "$workspace/injected"
grep -Fx 'path with spaces;$(touch injected)' "$ARG_LOG" >/dev/null
grep -Fx 'authoritative-status=PASS' "$GITHUB_OUTPUT" >/dev/null

if MODE=proof "$template_root/run.sh" 2>/dev/null; then
  echo 'proof mode must be rejected' >&2
  exit 1
fi

if MODE='check; touch injected-2' "$template_root/run.sh" 2>/dev/null; then
  echo 'malicious mode must be rejected' >&2
  exit 1
fi
test ! -e "$workspace/injected-2"

MODE=scope BASE='main; touch injected-3' INTENT='intent.json' \
  "$template_root/run.sh"
test ! -e "$workspace/injected-3"
grep -Fx 'main; touch injected-3' "$ARG_LOG" >/dev/null

MODE=fresh PROOF='proof `touch injected-4`.json' "$template_root/run.sh"
test ! -e "$workspace/injected-4"
grep -Fx 'proof `touch injected-4`.json' "$ARG_LOG" >/dev/null

echo 'GitHub Action template PASS'
