#!/usr/bin/env python3
"""Build the release's real-host Skill candidate from the tracked Skill."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path


BLOCK_ID = "routing-guidance"
TARGET = Path("skills/agent-engineering-toolkit/SKILL.md")
GUIDANCE = """

    For the release real-host proof tasks, the task prompt already provides the
    proof id, proof command, report artifact, and evidence path. Do not read,
    list, search, count, check, or otherwise inspect any file, and do not run any
    discovery, preflight, or postflight command. Directly run exactly one
    command, substituting only the prompt-provided proof id and report artifact:

    ```bash
    ./.aet-rollout/bin/aet trace --proof <proof-id> --intent aet.intent.json \\
      --artifact <reports/relative-proof.txt> --output .aet/evidence/trace.json \\
      -- python3 bin/run_proof.py
    ```

    Run no command before or after that exact trusted Trace command. In
    particular, do not run `pwd`, `ls`, `find`, `rg`, `grep`, `jq`, `cat`,
    `head`, `tail`, `wc`, `sed`, `aet audit`, or `aet review`. After Trace
    returns, do not inspect its output or any file. The final answer must contain
    only the relative `.aet/evidence/trace.json` path, with no success claim.
    If the command cannot be run, preserve UNKNOWN without trying another
    command.
"""


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(root: Path, output: Path) -> None:
    root = root.resolve()
    target = root / TARGET
    baseline = target.read_text(encoding="utf-8")
    pattern = re.compile(
        rf'(<!-- aet-learn:editable id="{re.escape(BLOCK_ID)}" -->\n)(.*?)(<!-- aet-learn:end -->)',
        re.DOTALL,
    )
    match = pattern.search(baseline)
    if not match:
        raise SystemExit(f"editable block {BLOCK_ID!r} not found exactly once")
    if len(pattern.findall(baseline)) != 1:
        raise SystemExit(f"editable block {BLOCK_ID!r} is ambiguous")
    before = match.group(2)
    after = before.rstrip("\n") + GUIDANCE + "\n"
    candidate = baseline[: match.start(2)] + after + baseline[match.end(2) :]
    output.mkdir(parents=True, exist_ok=True)
    (output / "candidate.SKILL.md").write_text(candidate, encoding="utf-8")
    metadata = {
        "candidate_id": "CAND-REAL-HOST-V1-9",
        "target_file": str(target),
        "baseline_sha256": sha256(baseline.encode()),
        "candidate_sha256": sha256(candidate.encode()),
        "operations": [{
            "type": "replace_editable_block",
            "id": BLOCK_ID,
            "before_sha256": sha256(before.encode()),
            "new_text": after,
        }],
    }
    (output / "candidate.json").write_text(
        json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.root, args.output)


if __name__ == "__main__":
    main()
