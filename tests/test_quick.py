from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import contextmanager, redirect_stdout
from io import StringIO
from pathlib import Path

from aet.cli import main
from aet.narrative import render_investigated_finding, select_language


class QuickCommandTests(unittest.TestCase):
    def test_quick_check_is_bounded_and_keeps_authoritative_statuses(self) -> None:
        root = Path(__file__).parent / "fixtures" / "broken_project"
        output = StringIO()
        with redirect_stdout(output):
            result = main(["quick", "check", str(root), "--format", "json"])
        data = json.loads(output.getvalue())
        self.assertEqual(result, 1)
        self.assertEqual(data["report_kind"], "quick_check_preflight")
        self.assertLessEqual(len(data["findings"]), 5)
        self.assertEqual(
            data["authoritative_status_set"],
            ["PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"],
        )
        self.assertEqual(data["host_investigation"]["stop_after"], "report_emitted")

    def test_quick_scope_does_not_turn_path_mismatch_into_out_of_scope(self) -> None:
        with _repository() as (root, base):
            intent = root / "aet.intent.json"
            intent.write_text(json.dumps({
                "intent": "Change only src.",
                "changed_path_budget": 2,
                "allowed_paths": ["src/**"],
                "required_proofs": [{"id": "tests", "command": "python -m unittest", "evidence": ["src/app.py"]}],
            }), encoding="utf-8")
            (root / "docs").mkdir()
            (root / "docs" / "extra.md").write_text("extra\n", encoding="utf-8")
            output = StringIO()
            with redirect_stdout(output):
                result = main([
                    "quick", "scope", str(root), "--base", base,
                    "--intent", str(intent), "--format", "json",
                ])
            data = json.loads(output.getvalue())
        self.assertEqual(result, 1)
        self.assertEqual(data["disposition"], "POSSIBLE_SCOPE_EXPANSION")
        self.assertNotEqual(data["disposition"], "OUT_OF_SCOPE")
        self.assertIn("cannot establish OUT_OF_SCOPE", data["guardrail"])

    def test_quick_scope_without_intent_preserves_deterministic_observations(self) -> None:
        with _repository() as (root, base):
            output = StringIO()
            with redirect_stdout(output):
                result = main(["quick", "scope", str(root), "--base", base, "--format", "json"])
            data = json.loads(output.getvalue())
        self.assertEqual(result, 0)
        self.assertEqual(data["authoritative_status"], "UNKNOWN")
        self.assertEqual(data["disposition"], "INSUFFICIENT_INTENT")
        self.assertTrue(data["observations"])

    def test_quick_proof_writes_one_receipt_and_nonzero_is_not_success(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proof = root / "proof.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                result = main([
                    "quick", "proof", "--output", str(proof), "--",
                    sys.executable, "-c", "raise SystemExit(7)",
                ])
            finally:
                os.chdir(previous)
            data = json.loads(proof.read_text(encoding="utf-8"))
            self.assertEqual(result, 7)
            self.assertEqual(data["schema_version"], "aet-proof-receipt/v2")
            self.assertEqual(data["authoritative_status"], "FAIL")
            self.assertEqual(data["command"]["exit_code"], 7)
            self.assertEqual([path.name for path in root.iterdir()], ["proof.json"])

    def test_quick_proof_binds_selected_executable_and_declared_environment(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proof = root / "proof.json"
            previous = Path.cwd()
            previous_value = os.environ.get("AET_QUICK_TEST_ENV")
            try:
                os.chdir(root)
                os.environ["AET_QUICK_TEST_ENV"] = "bound-value"
                self.assertEqual(main([
                    "quick", "proof", "--output", str(proof),
                    "--env-binding", "AET_QUICK_TEST_ENV", "--",
                    sys.executable, "-c", "pass",
                ]), 0)
            finally:
                os.chdir(previous)
                if previous_value is None:
                    os.environ.pop("AET_QUICK_TEST_ENV", None)
                else:
                    os.environ["AET_QUICK_TEST_ENV"] = previous_value
            environment = json.loads(proof.read_text(encoding="utf-8"))["binding"]["environment"]
        self.assertEqual(environment["selected_executable"]["path"], str(Path(sys.executable).resolve()))
        self.assertEqual(environment["explicit_environment"][0]["name"], "AET_QUICK_TEST_ENV")
        self.assertNotIn("bound-value", json.dumps(environment))

    def test_missing_required_environment_binding_preserves_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            proof = root / "proof.json"
            previous = Path.cwd()
            previous_value = os.environ.pop("AET_QUICK_MISSING_ENV", None)
            try:
                os.chdir(root)
                result = main([
                    "quick", "proof", "--output", str(proof),
                    "--env-binding", "AET_QUICK_MISSING_ENV", "--",
                    sys.executable, "-c", "pass",
                ])
                fresh = _fresh(proof)
            finally:
                os.chdir(previous)
                if previous_value is not None:
                    os.environ["AET_QUICK_MISSING_ENV"] = previous_value
            receipt = json.loads(proof.read_text(encoding="utf-8"))
        self.assertEqual(result, 0)
        self.assertEqual(receipt["authoritative_status"], "UNKNOWN")
        self.assertEqual(receipt["binding"]["status"], "UNKNOWN")
        self.assertEqual(fresh["freshness_state"], "UNKNOWN")

    def test_quick_fresh_distinguishes_unrelated_and_relevant_changes(self) -> None:
        with _repository() as (root, _):
            proof = root / ".aet" / "proof.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main([
                    "quick", "proof", "--output", str(proof),
                    "--relevant-path", "src/app.py", "--",
                    sys.executable, "-c", "pass",
                ]), 0)
                (root / "README.md").write_text("unrelated\n", encoding="utf-8")
                output = StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(["quick", "fresh", "--proof", str(proof), "--format", "json"]), 0)
                unrelated = json.loads(output.getvalue())
                (root / "src" / "app.py").write_text("changed\n", encoding="utf-8")
                output = StringIO()
                with redirect_stdout(output):
                    self.assertEqual(main(["quick", "fresh", "--proof", str(proof), "--format", "json"]), 1)
                relevant = json.loads(output.getvalue())
            finally:
                os.chdir(previous)
        self.assertEqual(unrelated["freshness_state"], "RELEVANT_FILES_MATCH")
        self.assertEqual(relevant["freshness_state"], "RELEVANT_FILES_CHANGED")

    def test_quick_fresh_reports_exact_and_head_only_changes(self) -> None:
        with _repository() as (root, _):
            proof = root / ".aet" / "proof.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main([
                    "quick", "proof", "--output", str(proof),
                    "--relevant-path", "src/app.py", "--",
                    sys.executable, "-c", "pass",
                ]), 0)
                exact = _fresh(proof)
                _git(root, "add", "src/app.py")
                _git(root, "commit", "-m", "relevant baseline")
                head_only = _fresh(proof)
            finally:
                os.chdir(previous)
        self.assertEqual(exact["freshness_state"], "EXACT_MATCH")
        self.assertEqual(head_only["freshness_state"], "HEAD_CHANGED_RELEVANT_FILES_MATCH")

    def test_quick_fresh_accepts_legacy_evidence_receipt(self) -> None:
        with _repository() as (root, _):
            trace = root / ".aet" / "trace.json"
            receipt = root / ".aet" / "legacy-receipt.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main([
                    "trace", "--output", str(trace), "--",
                    sys.executable, "-c", "pass",
                ]), 0)
                self.assertEqual(main([
                    "evidence", "receipt", "--report", str(trace),
                    "--output", str(receipt),
                ]), 0)
                result = _fresh(receipt)
            finally:
                os.chdir(previous)
        self.assertEqual(result["freshness_state"], "EXACT_MATCH")
        self.assertEqual(result["legacy"]["report_kind"], "evidence_receipt")

    def test_quick_fresh_reports_artifact_environment_and_unknown_changes(self) -> None:
        with _repository() as (root, _):
            previous = Path.cwd()
            try:
                os.chdir(root)
                artifact_proof = root / ".aet" / "artifact-proof.json"
                self.assertEqual(main([
                    "quick", "proof", "--output", str(artifact_proof),
                    "--artifact", "report.txt", "--",
                    sys.executable, "-c", "from pathlib import Path; Path('report.txt').write_text('pass')",
                ]), 0)
                (root / "report.txt").write_text("changed\n", encoding="utf-8")
                artifact = _fresh(artifact_proof)

                (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
                environment_proof = root / ".aet" / "environment-proof.json"
                self.assertEqual(main([
                    "quick", "proof", "--output", str(environment_proof),
                    "--relevant-path", "src/app.py", "--",
                    sys.executable, "-c", "pass",
                ]), 0)
                (root / "uv.lock").write_text("version = 2\n", encoding="utf-8")
                environment = _fresh(environment_proof)

                unknown_proof = root / ".aet" / "unknown-proof.json"
                self.assertEqual(main([
                    "quick", "proof", "--output", str(unknown_proof),
                    "--relevant-path", "src/app.py", "--",
                    sys.executable, "-c", "pass",
                ]), 0)
                (root / "src" / "app.py").unlink()
                unknown = _fresh(unknown_proof)
            finally:
                os.chdir(previous)
        self.assertEqual(artifact["freshness_state"], "ARTIFACT_CHANGED")
        self.assertEqual(environment["freshness_state"], "ENVIRONMENT_CHANGED")
        self.assertEqual(unknown["freshness_state"], "UNKNOWN")

    def test_quick_fresh_preserves_unknown_artifact_binding(self) -> None:
        with _repository() as (root, _):
            proof = root / ".aet" / "proof.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main([
                    "quick", "proof", "--output", str(proof),
                    "--artifact", "reports/missing.json", "--",
                    sys.executable, "-c", "pass",
                ]), 1)
                result = _fresh(proof)
            finally:
                os.chdir(previous)
        self.assertEqual(result["freshness_state"], "UNKNOWN")

    def test_language_is_chinese_only_for_chinese_slash_request(self) -> None:
        self.assertEqual(select_language(request="/aet-scope 请检查范围", slash_command=True), "zh-CN")
        self.assertEqual(select_language(request="请检查范围", slash_command=False), "en")
        self.assertEqual(select_language(request="/aet-scope check scope", slash_command=True), "en")

    def test_bilingual_narrative_preserves_evidence_references(self) -> None:
        finding = {
            "conclusion": "Payment change needs investigation.",
            "confirmed_facts": [{
                "statement": "src/payment/order.py changed",
                "evidence_refs": ["evidence://git/1"],
            }],
            "engineering_judgment": "No necessity is established.",
            "counter_explanation": {
                "statement": "A shared interface may require the change.",
                "investigation_result": "UNRESOLVED",
                "evidence_refs": [],
            },
            "remaining_uncertainty": ["Another conversation may contain authorization."],
            "locations": [{"path": "src/payment/order.py", "line": 84}],
            "recommended_action": "Split the change or provide the dependency.",
            "evidence_refs": ["evidence://git/1"],
        }
        english = render_investigated_finding(finding, "en")
        chinese = render_investigated_finding(finding, "zh-CN")
        self.assertIn("evidence://git/1", english)
        self.assertIn("evidence://git/1", chinese)
        self.assertIn("反方解释", chinese)
        self.assertIn("Counter-explanation", english)


@contextmanager
def _repository():
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        _git(root, "init")
        _git(root, "config", "user.email", "aet@example.test")
        _git(root, "config", "user.name", "AET test")
        (root / "src").mkdir()
        (root / "src" / "app.py").write_text("base\n", encoding="utf-8")
        (root / "README.md").write_text("base\n", encoding="utf-8")
        (root / ".gitignore").write_text(".aet/\n", encoding="utf-8")
        _git(root, "add", ".")
        _git(root, "commit", "-m", "base")
        base = _git(root, "rev-parse", "HEAD").stdout.strip()
        (root / "src" / "app.py").write_text("updated\n", encoding="utf-8")
        yield root, base


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)


def _fresh(proof: Path) -> dict[str, object]:
    output = StringIO()
    with redirect_stdout(output):
        main(["quick", "fresh", "--proof", str(proof), "--format", "json"])
    return json.loads(output.getvalue())


if __name__ == "__main__":
    unittest.main()
