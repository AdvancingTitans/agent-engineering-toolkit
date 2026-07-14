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
from aet.evidence import compare_workspace_snapshots, workspace_snapshot
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

    def test_trace_reuses_only_an_exact_fresh_success_without_rerunning(self) -> None:
        with _review_repository() as (root, _):
            command = [sys.executable, "-c", "from pathlib import Path; p=Path('count.txt'); p.write_text(str(int(p.read_text())+1) if p.exists() else '1')"]
            output = root / ".aet" / "evidence" / "trace.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["trace", "--output", str(output), "--", *command]), 0)
                self.assertEqual(main(["trace", "--reuse-if-fresh", "--output", str(output), "--", *command]), 0)
            finally:
                os.chdir(previous)
            self.assertEqual((root / "count.txt").read_text(), "1")

    def test_trace_reuse_refuses_stale_or_mismatched_evidence_without_execution(self) -> None:
        with _review_repository() as (root, _):
            command = [sys.executable, "-c", "from pathlib import Path; Path('proof-ran').write_text('yes')"]
            output = root / ".aet" / "evidence" / "trace.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["trace", "--output", str(output), "--", *command]), 0)
                (root / "README.md").write_text("changed after proof\n", encoding="utf-8")
                with self.assertRaises(SystemExit):
                    main(["trace", "--reuse-if-fresh", "--output", str(output), "--", *command])
                with self.assertRaises(SystemExit):
                    main(["trace", "--reuse-if-fresh", "--output", str(output), "--", sys.executable, "-c", "raise SystemExit(9)"])
            finally:
                os.chdir(previous)
            self.assertEqual((root / "proof-ran").read_text(), "yes")

    def test_trace_reuse_distinguishes_commands_that_redact_to_the_same_argv(self) -> None:
        with _review_repository() as (root, _):
            output = root / ".aet" / "evidence" / "trace.json"
            first = [sys.executable, "-c", "pass", "--token first-secret-value"]
            second = [sys.executable, "-c", "pass", "--token second-secret-value"]
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["trace", "--output", str(output), "--", *first]), 0)
                self.assertIsNone(json.loads(output.read_text(encoding="utf-8"))["trace"]["argv_sha256"])
                with self.assertRaises(SystemExit):
                    main(["trace", "--reuse-if-fresh", "--output", str(output), "--", *second])
            finally:
                os.chdir(previous)

    def test_trace_reuse_refuses_tampered_log_or_declared_artifact(self) -> None:
        with _review_repository() as (root, _):
            command = [sys.executable, "-c", "from pathlib import Path; Path('report.txt').write_text('ok')"]
            output = root / ".aet" / "evidence" / "trace.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["trace", "--artifact", "report.txt", "--output", str(output), "--", *command]), 0)
                output.with_suffix(".stdout.log").write_text("tampered", encoding="utf-8")
                with self.assertRaises(SystemExit):
                    main(["trace", "--reuse-if-fresh", "--artifact", "report.txt", "--output", str(output), "--", *command])
            finally:
                os.chdir(previous)

    def test_trace_reuse_refuses_symlinked_logs_even_when_bytes_match(self) -> None:
        with _review_repository() as (root, _):
            command = [sys.executable, "-c", "print('ok')"]
            output = root / ".aet" / "evidence" / "trace.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["trace", "--output", str(output), "--", *command]), 0)
                stdout = output.with_suffix(".stdout.log")
                replacement = stdout.with_name("replacement.log")
                replacement.write_bytes(stdout.read_bytes())
                stdout.unlink()
                stdout.symlink_to(replacement)
                with self.assertRaises(SystemExit):
                    main(["trace", "--reuse-if-fresh", "--output", str(output), "--", *command])
            finally:
                os.chdir(previous)

    def test_trace_reuse_refuses_a_tampered_canonical_report(self) -> None:
        with _review_repository() as (root, _):
            command = [sys.executable, "-c", "print('ok')"]
            output = root / ".aet" / "evidence" / "trace.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["trace", "--output", str(output), "--", *command]), 0)
                report = json.loads(output.read_text(encoding="utf-8"))
                report["generated_at"] = "tampered"
                output.write_text(json.dumps(report), encoding="utf-8")
                with self.assertRaises(SystemExit):
                    main(["trace", "--reuse-if-fresh", "--output", str(output), "--", *command])
                with self.assertRaises(SystemExit):
                    main(["evidence", "pack", "--trace", str(output), "--output", str(root / ".aet" / "pack.json")])
            finally:
                os.chdir(previous)

    def test_evidence_receipt_is_compact_and_binds_the_canonical_report(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            trace = root / "trace.json"
            receipt = root / "receipt.json"
            self.assertEqual(main(["trace", "--output", str(trace), "--", sys.executable, "-c", "print('ok')"]), 0)
            self.assertEqual(main(["evidence", "receipt", "--report", str(trace), "--output", str(receipt)]), 0)
            data = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(data["report_kind"], "evidence_receipt")
            self.assertEqual(data["source"]["sha256"], _sha256(trace))
            self.assertEqual(data["source"]["report_kind"], "trace")
            self.assertEqual(data["execution"], {"status": "PASS", "exit_code": 0})
            self.assertNotIn("findings", data)
            self.assertNotIn("assets", data)

    def test_evidence_receipt_checks_live_freshness_and_cannot_replace_its_source(self) -> None:
        with _review_repository() as (root, _):
            trace = root / ".aet" / "trace.json"
            receipt = root / ".aet" / "receipt.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["trace", "--output", str(trace), "--", sys.executable, "-c", "pass"]), 0)
                original = trace.read_bytes()
                with self.assertRaises(SystemExit):
                    main(["evidence", "receipt", "--report", str(trace), "--output", str(trace)])
                self.assertEqual(trace.read_bytes(), original)
                (root / "README.md").write_text("changed\n", encoding="utf-8")
                self.assertEqual(main(["evidence", "receipt", "--report", str(trace), "--output", str(receipt)]), 0)
            finally:
                os.chdir(previous)
            data = json.loads(receipt.read_text(encoding="utf-8"))
            self.assertEqual(data["freshness"]["status"], "FAIL")

    def test_trace_captures_one_workspace_snapshot_per_result(self) -> None:
        from unittest import mock

        snapshot = {
            "status": "PASS", "head_sha": "a" * 40, "tracked_worktree_sha256": "b" * 64,
            "worktree_digest": "c" * 64, "untracked_manifest_sha256": "d" * 64, "digest": "e" * 64,
            "intent_sha256": None, "config_sha256": None, "control_files": {},
        }
        with TemporaryDirectory() as directory, mock.patch("aet.evidence.workspace_snapshot", return_value=snapshot) as capture:
            self.assertEqual(main(["trace", "--output", str(Path(directory) / "trace.json"), "--", sys.executable, "-c", "pass"]), 0)
            self.assertEqual(capture.call_count, 1)

    def test_trace_captures_declared_report_artifact_and_portable_pack(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "trace.json"
            report = root / "reports" / "junit.xml"
            command = [sys.executable, "-c", "from pathlib import Path; Path('reports').mkdir(); Path('reports/junit.xml').write_text('<testsuite token=supersecret/>')"]
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["trace", "--artifact", "reports/junit.xml", "--output", str(output), "--", *command]), 0)
                pack = root / "pack.json"
                self.assertEqual(main(["evidence", "pack", "--trace", str(output), "--output", str(pack)]), 0)
            finally:
                os.chdir(previous)
            trace = json.loads(output.read_text(encoding="utf-8"))
            artifact = trace["trace"]["artifacts"][0]
            self.assertEqual(artifact["requested_path"], "reports/junit.xml")
            self.assertEqual(artifact["status"], "PASS")
            self.assertNotIn("supersecret", output.read_text(encoding="utf-8"))
            self.assertEqual(artifact["sha256"], _sha256_text(artifact["content"]))
            portable = json.loads(pack.read_text(encoding="utf-8"))["components"]["trace"]["report"]["artifacts"][0]
            self.assertEqual(portable["content"], artifact["content"])
            self.assertEqual(portable["sha256"], artifact["sha256"])

    def test_trace_fails_closed_for_missing_or_outside_declared_artifact(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            output = root / "trace.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["trace", "--artifact", "reports/missing.xml", "--output", str(output), "--", sys.executable, "-c", "pass"]), 1)
                with self.assertRaises(SystemExit):
                    main(["trace", "--artifact", "../outside.xml", "--output", str(root / "outside.json"), "--", sys.executable, "-c", "raise SystemExit(99)"])
            finally:
                os.chdir(previous)
            trace = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(trace["trace"]["execution"], {"status": "PASS", "exit_code": 0})
            self.assertEqual(trace["trace"]["artifacts"][0]["status"], "UNKNOWN")
            self.assertEqual(trace["summary"]["UNKNOWN"], 1)

    def test_missing_declared_artifact_keeps_a_bound_proof_unknown(self) -> None:
        with _review_repository() as (root, base):
            _write_contract(root, budget=1, evidence=["aet.intent.json"])
            review_output = root / "review.json"
            trace = root / "trace.json"
            pack = root / "pack.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["review", ".", "--base", base, "--format", "json", "--output", str(review_output)]), 0)
                self.assertEqual(main(["trace", "--proof", "unit-tests", "--intent", "aet.intent.json", "--artifact", "reports/missing.xml", "--output", str(trace), "--", sys.executable, "-c", "pass"]), 1)
                self.assertEqual(main(["evidence", "pack", "--review", str(review_output), "--trace", str(trace), "--output", str(pack)]), 0)
            finally:
                os.chdir(previous)
            self.assertEqual(json.loads(pack.read_text(encoding="utf-8"))["proof_binding"]["status"], "UNKNOWN")

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

    def test_snapshot_distinguishes_intent_and_config_changes(self) -> None:
        with _review_repository() as (root, _):
            (root / "aet.intent.json").write_text('{"intent":"before"}', encoding="utf-8")
            before = workspace_snapshot(root)
            (root / "aet.intent.json").write_text('{"intent":"after"}', encoding="utf-8")
            self.assertEqual(compare_workspace_snapshots({"before": before, "after": workspace_snapshot(root)})["state"], "INTENT_CHANGED")
            (root / "aet.toml").write_text("[scan]\ninclude = []\nexclude = []\n", encoding="utf-8")
            config_before = workspace_snapshot(root)
            (root / "aet.toml").write_text("[scan]\ninclude = ['AGENTS.md']\nexclude = []\n", encoding="utf-8")
            self.assertEqual(compare_workspace_snapshots({"before": config_before, "after": workspace_snapshot(root)})["state"], "CONFIG_CHANGED")

    def test_snapshot_distinguishes_untracked_set_changes(self) -> None:
        with _review_repository() as (root, _):
            before = workspace_snapshot(root)
            (root / "new-report.md").write_text("untracked\n", encoding="utf-8")
            binding = compare_workspace_snapshots({"before": before, "after": workspace_snapshot(root)})
            self.assertEqual(binding["status"], "FAIL")
            self.assertEqual(binding["state"], "UNTRACKED_SET_CHANGED")


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


def _sha256_text(value: str) -> str:
    import hashlib

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    unittest.main()
