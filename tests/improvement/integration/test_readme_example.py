from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from aet.atlas.storage import build_evidence_atlas
from aet.improvement.cli.improve import (
    generate_agent_prompt,
    generate_improvements,
)


ROOT = Path(__file__).resolve().parents[3]
BUILDER = (
    ROOT / "examples/evidence-grounded-improvement/build_example.py"
)


class ReadmeImprovementExampleTests(unittest.TestCase):
    def test_same_bundle_drives_prompt_and_atlas_without_authority_loop(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            bundle = root / "bundle"
            improvements = root / "improvements"
            atlas = root / "atlas"
            subprocess.run(
                [sys.executable, str(BUILDER), "--output", str(bundle)],
                cwd=ROOT,
                check=True,
            )

            result = generate_improvements(bundle, output=improvements)
            prompt = generate_agent_prompt(
                "IMP-001",
                output=improvements,
            )
            built = build_evidence_atlas(
                bundle,
                output=atlas,
                perspective_ids=(
                    "claim-chain",
                    "conflicts",
                    "improvement-chain",
                ),
            )

            self.assertEqual(result["issue_count"], 1)
            self.assertEqual(prompt["status"], "PROPOSED")
            agent_task = (improvements / "agent-task.md").read_text(
                encoding="utf-8"
            )
            self.assertIn("ev-empty-result-regression", agent_task)
            self.assertIn(
                "examples/evidence-grounded-improvement/"
                "sample_project/tool_result.py",
                agent_task,
            )
            perspectives = {
                item["id"]: item for item in built["perspectives"]
            }
            self.assertEqual(
                perspectives["claim-chain"]["coverage_status"],
                "PASS",
            )
            self.assertEqual(
                perspectives["improvement-chain"]["coverage_status"],
                "UNKNOWN",
            )
            issues = json.loads(
                (improvements / "issues.json").read_text(encoding="utf-8")
            )
            self.assertEqual(
                issues[0]["finding_refs"],
                ["claim-empty-result-is-grounded"],
            )


if __name__ == "__main__":
    unittest.main()
