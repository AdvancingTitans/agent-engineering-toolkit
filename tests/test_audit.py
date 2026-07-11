from __future__ import annotations

import json
import unittest
from pathlib import Path

from aet.cli import main
from aet.discovery import discover_assets
from aet.reporters import report_data, render_sarif
from aet.rules import run_rules


FIXTURES = Path(__file__).parent / "fixtures"


class AuditTests(unittest.TestCase):
    def test_valid_fixture_has_no_findings(self) -> None:
        root = FIXTURES / "valid_project"
        findings = run_rules(root, discover_assets(root))
        self.assertEqual(findings, [])


    def test_broken_fixture_has_evidence_backed_failures(self) -> None:
        root = FIXTURES / "broken_project"
        findings = run_rules(root, discover_assets(root))
        identifiers = {finding.rule_id for finding in findings}
        self.assertTrue({"AET-CTX-001", "AET-CTX-002", "AET-SKL-002", "AET-SKL-004"} <= identifiers)
        self.assertTrue(all(finding.evidence for finding in findings))


    def test_sarif_is_machine_readable(self) -> None:
        root = FIXTURES / "broken_project"
        data = report_data(root, discover_assets(root), run_rules(root, discover_assets(root)))
        sarif = json.loads(render_sarif(data))
        self.assertEqual(sarif["version"], "2.1.0")
        self.assertTrue(sarif["runs"][0]["results"])


    def test_cli_exit_codes(self) -> None:
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as directory:
            output = Path(directory) / "report.json"
            self.assertEqual(main(["audit", str(FIXTURES / "valid_project"), "--format", "json", "--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text())["summary"]["FAIL"], 0)
            self.assertEqual(main(["audit", str(FIXTURES / "broken_project")]), 1)


if __name__ == "__main__":
    unittest.main()
