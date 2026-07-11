from __future__ import annotations

import json
import os
import subprocess
import sys
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

    def test_trace_records_successful_command_and_redacts_logs(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "trace.json"
            command = [sys.executable, "-c", "print('token=supersecret')"]
            self.assertEqual(main(["trace", "--output", str(output), "--", *command]), 0)
            trace = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(trace["trace"]["execution"]["exit_code"], 0)
            self.assertEqual(trace["trace"]["execution"]["status"], "PASS")
            self.assertNotIn("supersecret", output.read_text(encoding="utf-8"))
            stdout = output.with_suffix(".stdout.log")
            self.assertTrue(stdout.is_file())
            self.assertNotIn("supersecret", stdout.read_text(encoding="utf-8"))
            self.assertEqual(trace["trace"]["stdout"]["sha256"], _sha256(stdout))

    def test_trace_records_nonzero_exit_without_invalidating_trace(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "trace.json"
            self.assertEqual(main(["trace", "--output", str(output), "--", sys.executable, "-c", "raise SystemExit(7)"]), 7)
            trace = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(trace["trace"]["execution"], {"status": "FAIL", "exit_code": 7})
            self.assertEqual(trace["summary"]["FAIL"], 1)

    def test_evidence_pack_marks_missing_inputs_unknown_and_replaces_output_atomically(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "evidence-pack.json"
            output.write_text("old output", encoding="utf-8")
            self.assertEqual(main(["evidence", "pack", "--output", str(output)]), 0)
            pack = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(pack["components"]["audit"]["status"], "UNKNOWN")
            self.assertEqual(pack["components"]["review"]["status"], "UNKNOWN")
            self.assertEqual(pack["components"]["trace"]["status"], "UNKNOWN")
            self.assertFalse(list(Path(directory).glob(".evidence-pack.json.*")))

    def test_evidence_pack_validates_schema_and_keeps_source_hash_stable(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            invalid = root / "invalid.json"
            invalid.write_text('{"report_kind": "audit"}', encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["evidence", "pack", "--audit", str(invalid), "--output", str(root / "bad-pack.json")])

            audit = root / "audit.json"
            audit.write_text(json.dumps(_minimal_report("audit")), encoding="utf-8")
            first = root / "first.json"
            second = root / "second.json"
            self.assertEqual(main(["evidence", "pack", "--audit", str(audit), "--output", str(first)]), 0)
            self.assertEqual(main(["evidence", "pack", "--audit", str(audit), "--output", str(second)]), 0)
            self.assertEqual(
                json.loads(first.read_text(encoding="utf-8"))["components"]["audit"]["sha256"],
                json.loads(second.read_text(encoding="utf-8"))["components"]["audit"]["sha256"],
            )

    def test_clean_git_fixture_can_compile_audit_review_trace_and_pack(self) -> None:
        with _review_repository() as (root, base):
            _write_contract(root, budget=2, evidence=["aet.intent.json"])
            contract = json.loads((root / "aet.intent.json").read_text(encoding="utf-8"))
            contract["allowed_paths"].append(".aet/**")
            (root / "aet.intent.json").write_text(json.dumps(contract), encoding="utf-8")
            evidence = root / ".aet" / "evidence"
            audit = evidence / "audit.json"
            review_output = evidence / "review.json"
            trace = evidence / "trace.json"
            pack = evidence / "evidence-pack.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["audit", ".", "--format", "json", "--output", str(audit)]), 0)
                self.assertEqual(main(["review", ".", "--base", base, "--format", "json", "--output", str(review_output)]), 0)
                self.assertEqual(main(["trace", "--output", str(trace), "--", sys.executable, "-c", "print('ok')"]), 0)
                self.assertEqual(main([
                    "evidence", "pack", "--audit", str(audit), "--review", str(review_output), "--trace", str(trace), "--output", str(pack),
                ]), 0)
            finally:
                os.chdir(previous)
            compiled = json.loads(pack.read_text(encoding="utf-8"))
            self.assertTrue(all(component["status"] == "PASS" for component in compiled["components"].values()))
            self.assertEqual(compiled["components"]["trace"]["report"]["execution"]["status"], "PASS")
            self.assertEqual(compiled["snapshot_binding"]["state"], "EXACT_MATCH")

    def test_evidence_pack_marks_workspace_changes_stale_without_overriding_proof(self) -> None:
        with _review_repository() as (root, base):
            _write_contract(root, budget=1, evidence=["aet.intent.json"])
            evidence = root / ".aet" / "evidence"
            audit = evidence / "audit.json"
            review_output = evidence / "review.json"
            trace = evidence / "trace.json"
            pack = evidence / "evidence-pack.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["audit", ".", "--format", "json", "--output", str(audit)]), 0)
                self.assertEqual(main(["review", ".", "--base", base, "--format", "json", "--output", str(review_output)]), 0)
                self.assertEqual(main(["trace", "--proof", "unit-tests", "--intent", "aet.intent.json", "--output", str(trace), "--", sys.executable, "-c", "pass"]), 0)
                (root / "README.md").write_text("changed after proof\n", encoding="utf-8")
                self.assertEqual(main(["evidence", "pack", "--audit", str(audit), "--review", str(review_output), "--trace", str(trace), "--output", str(pack)]), 0)
            finally:
                os.chdir(previous)
            compiled = json.loads(pack.read_text(encoding="utf-8"))
            self.assertEqual(compiled["proof_binding"]["status"], "PASS")
            self.assertEqual(compiled["snapshot_binding"]["status"], "FAIL")
            self.assertEqual(compiled["snapshot_binding"]["state"], "HEAD_MATCH_WORKTREE_DIFFERS")


class _review_repository:
    def __enter__(self) -> tuple[Path, str]:
        self.temporary_directory = TemporaryDirectory()
        self.root = Path(self.temporary_directory.name)
        _git(self.root, "init")
        _git(self.root, "config", "user.email", "aet@example.test")
        _git(self.root, "config", "user.name", "AET test")
        (self.root / "README.md").write_text("base\n", encoding="utf-8")
        (self.root / ".gitignore").write_text(".aet/\n", encoding="utf-8")
        _git(self.root, "add", "README.md", ".gitignore")
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


def _minimal_report(kind: str) -> dict:
    return {
        "schema_version": "0.3.0",
        "report_kind": kind,
        "generated_at": "2026-07-11T00:00:00+00:00",
        "root": "/tmp/example",
        "assets": [],
        "findings": [],
        "summary": {"PASS": 0, "FAIL": 0, "UNKNOWN": 0, "NOT_APPLICABLE": 0},
    }


def _sha256(path: Path) -> str:
    import hashlib

    return hashlib.sha256(path.read_bytes()).hexdigest()


if __name__ == "__main__":
    unittest.main()
