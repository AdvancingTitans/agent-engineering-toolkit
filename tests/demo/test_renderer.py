import json
import unittest
from pathlib import Path

from aet.demo.models import DemoResult
from aet.demo.renderer import render_json, render_markdown, render_text


ROOT = Path(__file__).resolve().parents[2]


def result() -> DemoResult:
    return DemoResult(
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


class DemoRendererTests(unittest.TestCase):
    def test_text_matches_snapshot_without_ansi(self) -> None:
        rendered = render_text(result())
        expected = (ROOT / "tests/snapshots/demo_stale_proof.txt").read_text()
        self.assertEqual(rendered, expected)
        self.assertNotIn("\x1b", rendered)

    def test_json_matches_snapshot_and_has_trailing_newline(self) -> None:
        rendered = render_json(result())
        expected = (ROOT / "tests/snapshots/demo_stale_proof.json").read_text()
        self.assertEqual(rendered, expected)
        self.assertTrue(rendered.endswith("\n"))
        self.assertEqual(json.loads(rendered)["network_calls"], 0)

    def test_markdown_is_closed_and_escapes_diagnostics(self) -> None:
        unsafe = DemoResult(
            **{
                **result().to_dict(),
                "overall_status": "FAIL",
                "diagnostics": ("bad | `text`\x01",),
            }
        )
        rendered = render_markdown(unsafe)
        self.assertIn("bad \\| \\`text\\`�", rendered)
        self.assertEqual(rendered.count("```") % 2, 0)
