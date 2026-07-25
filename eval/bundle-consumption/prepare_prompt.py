#!/usr/bin/env python3
"""Render one SDK-free prompt containing the ten synthetic Bundle scenarios."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from aet.bundle import validate_bundle


def build_prompt(catalog_path: Path, bundle_root: Path) -> str:
    catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
    scenarios: list[dict[str, Any]] = []
    for entry in catalog["scenarios"]:
        bundle = validate_bundle(bundle_root / entry["scenario_id"])
        scenarios.append(
            {
                "scenario_id": entry["scenario_id"],
                "bundle_id": bundle["manifest"]["bundle"]["id"],
                "question": bundle["manifest"]["investigation"]["question"],
                "target_claim_id": bundle["claims"][0]["id"],
                "allowed_evidence_refs": [
                    item["id"] for item in bundle["evidence"]
                ],
                "observation_refs_not_evidence": [
                    item["id"] for item in bundle["observations"]
                ],
                "required_counter_evidence_refs": bundle["claims"][0][
                    "counter_evidence_refs"
                ],
                "claims": bundle["claims"],
                "evidence": bundle["evidence"],
                "observations": bundle["observations"],
                "diagnostics": bundle["diagnostics"],
                "conflicts": bundle["conflicts"],
            }
        )
    payload = json.dumps(
        {"scenarios": scenarios},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"""You are evaluating ten independent Portable Evidence Bundles.
No SDK or AET runtime is available. Use only the supplied JSON.

For each scenario:
- create exactly one conclusion for target_claim_id;
- cite only IDs declared in that scenario;
- claim_refs must be exactly [target_claim_id];
- evidence_refs must be a subset of allowed_evidence_refs; when
  allowed_evidence_refs is empty, evidence_refs must be [];
- counter_evidence_refs must exactly equal required_counter_evidence_refs;
- IDs in observation_refs_not_evidence must never appear in evidence_refs or
  counter_evidence_refs;
- preserve unknown, conflicted, truncated, content-identity, and non-current
  freshness limitations;
- include every counter_evidence_ref declared by the target Claim;
- never treat an Observation as Evidence;
- never infer that an event did not happen merely because evidence is missing;
- use accept only for a supported Claim with current corroborated or reproduced
  Evidence; otherwise use request_investigation or unknown.

Return JSON only, with this shape:
{{
  "reviews": [
    {{
      "scenario_id": "...",
      "review": {{
        "protocol": {{"name": "portable-review-result", "version": "1.0"}},
        "bundle_id": "...",
        "conclusions": [{{
          "id": "...",
          "statement": "...",
          "disposition": "accept|request_change|request_investigation|unknown",
          "claim_refs": ["..."],
          "evidence_refs": ["..."],
          "counter_evidence_refs": ["..."],
          "reasoning_summary": "...",
          "limitations": ["..."],
          "next_action": "..."
        }}],
        "unresolved_questions": ["..."]
      }}
    }}
  ]
}}

SCENARIOS_JSON:
{payload}
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--bundle-root", type=Path, required=True)
    args = parser.parse_args()
    print(build_prompt(args.catalog, args.bundle_root), end="")


if __name__ == "__main__":
    main()
