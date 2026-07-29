import json
import unittest
from dataclasses import FrozenInstanceError
from pathlib import Path

from aet.demo.models import DemoOptions, DemoResult


ROOT = Path(__file__).resolve().parents[2]


class DemoModelsTests(unittest.TestCase):
    def test_result_is_immutable_and_serializable(self) -> None:
        result = DemoResult(
            schema_version="aet-demo-result/v1",
            demo_id="stale-proof",
            overall_status="PASS",
            execution_status="PASS",
            before_state="EXACT_MATCH",
            after_state="RELEVANT_FILES_CHANGED",
            proof_path=None,
            workspace_path=None,
            diagnostics=(),
        )
        self.assertEqual(result.to_dict()["network_calls"], 0)
        with self.assertRaises(FrozenInstanceError):
            result.overall_status = "FAIL"  # type: ignore[misc]

    def test_options_have_safe_local_defaults(self) -> None:
        options = DemoOptions()
        self.assertEqual(options.format, "text")
        self.assertFalse(options.keep)
        self.assertIsNone(options.output)

    def test_demo_schemas_are_valid_json_and_pin_contracts(self) -> None:
        manifest = json.loads(
            (ROOT / "schemas/demo/v1/demo-manifest.schema.json").read_text()
        )
        result = json.loads(
            (ROOT / "schemas/demo/v1/demo-result.schema.json").read_text()
        )
        self.assertEqual(
            manifest["properties"]["schema_version"]["const"],
            "aet-demo-manifest/v1",
        )
        self.assertEqual(
            result["properties"]["schema_version"]["const"],
            "aet-demo-result/v1",
        )
        self.assertEqual(result["properties"]["network_calls"]["minimum"], 0)
        self.assertFalse(result["additionalProperties"])
