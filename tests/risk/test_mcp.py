from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aet.atlas.storage import build_evidence_atlas
from aet.atlas.validator import validate_evidence_atlas
from aet.bundle import validate_bundle
from aet.mcp_server import call_tool
from aet.risk.diagnose import diagnose_risk
from aet.risk.models import to_primitive


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/risk"
MINIMAL_BUNDLE = ROOT / "tests/fixtures/evidence-bundles/minimal"
CREATED_AT = "2026-08-01T00:00:00Z"


class RiskMcpAndAtlasTests(unittest.TestCase):
    def test_mcp_is_read_only_and_matches_python_api(self) -> None:
        inputs = (
            FIXTURES / "codex-compound.jsonl",
            FIXTURES / "intent-v2.json",
            FIXTURES / "risk-policy.json",
        )
        before = {path: path.read_bytes() for path in inputs}
        actual = call_tool(
            "aet_risk_diagnose",
            {
                "run": str(inputs[0]),
                "intent": str(inputs[1]),
                "policy": str(inputs[2]),
                "created_at": CREATED_AT,
            },
        )
        expected = to_primitive(
            diagnose_risk(
                run_path=inputs[0],
                intent_path=inputs[1],
                policy_path=inputs[2],
                now=CREATED_AT,
            )
        )
        self.assertEqual(expected, actual)
        self.assertEqual(before, {path: path.read_bytes() for path in inputs})
        self.assertNotIn("overall_score", actual)
        self.assertTrue(
            all(item["authority"] == "PROPOSED" for item in actual["interventions"])
        )

    def test_atlas_projects_only_bundle_resolved_diagnosis_references(self) -> None:
        diagnosis = to_primitive(
            diagnose_risk(
                run_path=FIXTURES / "codex-compound.jsonl",
                intent_path=FIXTURES / "intent-v2.json",
                policy_path=FIXTURES / "risk-policy.json",
                now=CREATED_AT,
            )
        )
        resolved_ref = {
            "ref": "src-001",
            "record_id": "src-001",
            "source_order_id": None,
            "source_type": "bundle",
        }
        for finding in diagnosis["findings"]:
            if finding["status"] == "FAIL":
                finding["evidence_refs"] = [resolved_ref]
        for pathway in diagnosis["pathways"]:
            pathway["ordered_refs"] = [resolved_ref]
        for intervention in diagnosis["interventions"]:
            intervention["rationale_refs"] = [resolved_ref]

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis_path = root / "diagnosis.json"
            diagnosis_path.write_text(json.dumps(diagnosis), encoding="utf-8")
            atlas = root / "atlas"
            built = build_evidence_atlas(
                MINIMAL_BUNDLE,
                output=atlas,
                risk_diagnosis=diagnosis_path,
            )
            validation = validate_evidence_atlas(
                atlas / "atlas-manifest.json",
                MINIMAL_BUNDLE,
            )

        perspective = next(
            item for item in built["perspectives"] if item["id"] == "behavioural-risk"
        )
        risk_nodes = [
            item for item in built["graph"]["nodes"]
            if "behavioural-risk" in item.get("tags", [])
        ]
        bundle = validate_bundle(MINIMAL_BUNDLE)
        bundle_record_ids = {
            item["id"]
            for collection in ("sources", "observations", "evidence", "claims")
            for item in bundle[collection]
        }
        self.assertEqual("aet-evidence-atlas-manifest/1.0", validation["schema_version"])
        self.assertEqual("PASS", perspective["coverage_status"])
        self.assertTrue(risk_nodes)
        self.assertTrue(
            all(
                ref["record_id"] in bundle_record_ids
                for item in risk_nodes
                for ref in item["source_refs"]
            )
        )
        self.assertTrue(
            all(
                item["authority"] == "PROPOSED"
                for item in risk_nodes
                if item["type"] == "recommendation"
            )
        )
        self.assertNotIn("overall_score", built["graph"])


if __name__ == "__main__":
    unittest.main()
