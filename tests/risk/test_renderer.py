from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aet.risk.diagnose import diagnose_risk
from aet.risk.errors import RiskInputError
from aet.risk.renderer import render_json, render_markdown, write_outputs


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/risk"


class RiskRendererTests(unittest.TestCase):
    def setUp(self) -> None:
        self.result = diagnose_risk(
            run_path=FIXTURES / "codex-compound.jsonl",
            intent_path=FIXTURES / "intent-v2.json",
            policy_path=FIXTURES / "risk-policy.json",
            now="2026-08-01T00:00:00Z",
        )

    def test_json_and_markdown_render_vector_and_limitations(self) -> None:
        payload = render_json(self.result)
        report = render_markdown(self.result)
        self.assertIn('"goal_divergence_indicator"', payload)
        self.assertNotIn("overall_score", payload)
        self.assertIn("Does not prove", report)

    def test_outputs_are_atomic_and_symlink_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            json_out = root / "risk.json"
            md_out = root / "risk.md"
            write_outputs(self.result, json_out, md_out)
            original = json_out.read_bytes()
            link = root / "link.json"
            link.symlink_to(json_out)
            with self.assertRaises(RiskInputError):
                write_outputs(self.result, link, root / "other.md")
            self.assertEqual(json_out.read_bytes(), original)

    def test_same_output_path_is_rejected_before_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "same"
            with self.assertRaises(RiskInputError):
                write_outputs(self.result, path, path)
            self.assertFalse(path.exists())

    def test_existing_report_is_preserved(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "risk.json"
            path.write_text("keep", encoding="utf-8")
            with self.assertRaises(RiskInputError):
                write_outputs(self.result, path)
            self.assertEqual("keep", path.read_text(encoding="utf-8"))

    def test_second_publish_failure_rolls_back_first_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            json_out = root / "risk.json"
            md_out = root / "risk.md"
            real_link = __import__("os").link
            calls = 0

            def fail_second(source: Path, target: Path, **kwargs: object) -> None:
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("controlled publish failure")
                real_link(source, target, **kwargs)

            with patch("aet.risk.renderer.os.link", side_effect=fail_second):
                with self.assertRaises(RiskInputError):
                    write_outputs(self.result, json_out, md_out)
            self.assertFalse(json_out.exists())
            self.assertFalse(md_out.exists())


if __name__ == "__main__":
    unittest.main()
