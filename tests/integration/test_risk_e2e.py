from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aet.risk.diagnose import diagnose_risk
from aet.risk.models import Status
from aet.risk.renderer import render_json, write_outputs
from aet.run_normalization import normalize_run, write_normalized_run


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/risk"


class RiskEndToEndTests(unittest.TestCase):
    def test_native_normalize_diagnose_validate_render_chain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            normalized = normalize_run(
                "codex",
                FIXTURES / "codex-compound.jsonl",
                generation_id="generation-0",
            )
            run_dir = root / "run"
            write_normalized_run(normalized, run_dir)
            diagnosis = diagnose_risk(
                run_path=run_dir,
                intent_path=FIXTURES / "intent-v2.json",
                policy_path=FIXTURES / "risk-policy.json",
                now="2026-08-01T00:00:00Z",
            )
            self.assertEqual({item.status for item in diagnosis.findings}, {Status.FAIL})
            json_out = root / "diagnosis.json"
            md_out = root / "diagnosis.md"
            write_outputs(diagnosis, json_out, md_out)
            self.assertEqual(json.loads(json_out.read_text())["schema_version"], "aet-risk-diagnosis/1.0")
            self.assertIn("Risk vector", md_out.read_text())


if __name__ == "__main__":
    unittest.main()
