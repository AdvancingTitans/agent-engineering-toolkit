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

    For the release real-host proof tasks, use the smallest exact workflow:
    use the proof id and report artifact named in the task prompt, bind them to
    `--intent aet.intent.json`, and run exactly one command of this form:

    ```bash
    ./.aet-rollout/bin/aet trace --proof <proof-id> --intent aet.intent.json \\
      --artifact <reports/relative-proof.txt> --output .aet/evidence/trace.json \\
      -- python3 bin/run_proof.py
    ```

    Cite the relative `.aet/evidence/trace.json` path in the final answer.
    Do not run extra `aet audit` or `aet review` commands. Preserve UNKNOWN if the one
    proof command cannot produce fresh evidence.
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
