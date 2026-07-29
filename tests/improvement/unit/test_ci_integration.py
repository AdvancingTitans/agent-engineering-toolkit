from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


class ImprovementCIIntegrationTests(unittest.TestCase):
    def test_workflow_is_deterministic_and_non_blocking(self) -> None:
        workflow = (
            ROOT / ".github/workflows/aet-improvement.yml"
        ).read_text(encoding="utf-8")

        self.assertIn("AET Improvement Summary", workflow)
        self.assertIn('continue-on-error: true', workflow)
        self.assertIn("This comment does not block merge", workflow)
        self.assertIn("aet improve", workflow)
        self.assertNotIn("openai", workflow.lower())
        self.assertNotIn("anthropic", workflow.lower())


if __name__ == "__main__":
    unittest.main()
