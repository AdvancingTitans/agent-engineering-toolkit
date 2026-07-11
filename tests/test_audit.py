from __future__ import annotations

import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from aet.cli import main
from aet.discovery import discover_assets
from aet.reporters import report_data, render_sarif
from aet.review import review
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

    def test_review_accepts_a_scoped_contract_with_local_proof_evidence(self) -> None:
        with _review_repository() as (root, base):
            _write_contract(root, budget=3, evidence=["tests/test_widget.py"])
            (root / "src").mkdir()
            (root / "src" / "widget.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_widget.py").write_text("assert True\n", encoding="utf-8")
            findings, metadata = review(root, base, Path("aet.intent.json"))
            self.assertEqual(metadata["changed_paths"], ["aet.intent.json", "src/widget.py", "tests/test_widget.py"])
            self.assertTrue(findings)
            self.assertTrue(all(finding.status.value == "PASS" for finding in findings))
            self.assertEqual(main(["review", str(root), "--base", base]), 0)

    def test_review_rejects_out_of_scope_paths_and_missing_proof_evidence(self) -> None:
        with _review_repository() as (root, base):
            _write_contract(root, budget=4, evidence=["tests/missing.py"])
            (root / "src").mkdir()
            (root / "src" / "widget.py").write_text("VALUE = 1\n", encoding="utf-8")
            (root / "tests").mkdir()
            (root / "tests" / "test_widget.py").write_text("assert True\n", encoding="utf-8")
            (root / "secrets.txt").write_text("not approved\n", encoding="utf-8")
            findings, _ = review(root, base, Path("aet.intent.json"))
            self.assertEqual(
                {(finding.rule_id, finding.status.value) for finding in findings if finding.status.value == "FAIL"},
                {("AET-REV-003", "FAIL"), ("AET-REV-004", "FAIL")},
            )


class _review_repository:
    def __enter__(self) -> tuple[Path, str]:
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "aet@example.test")
        _git(self.root, "config", "user.name", "AET test")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        _git(self.root, "add", "README.md")
        _git(self.root, "commit", "-m", "base")
        return self.root, _git(self.root, "rev-parse", "HEAD").stdout.strip()

    def __exit__(self, *_: object) -> None:
        self.temporary_directory.cleanup()


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)


def _write_contract(root: Path, *, budget: int, evidence: list[str]) -> None:
    (root / "aet.intent.json").write_text(json.dumps({
        "intent": "Add a focused widget with tests.",
        "changed_path_budget": budget,
        "allowed_paths": ["aet.intent.json", "src/**", "tests/**"],
        "required_proofs": [{
            "id": "unit-tests",
            "command": "python -m unittest discover -s tests",
            "evidence": evidence,
        }],
    }), encoding="utf-8")


if __name__ == "__main__":
    unittest.main()
