"""Audit feedback must be reproducible before it can drive adoption-grade learning."""

from __future__ import annotations

import json
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from aet.audit_feedback import AuditFeedbackError, record_audit_feedback
from aet.models import Evidence, Finding, Severity, Status


class AuditFeedbackTests(unittest.TestCase):
    def test_false_negative_requires_and_hashes_a_reproducible_fixture(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture"
            fixture.mkdir()
            (fixture / "AGENTS.md").write_text("# Instructions\n", encoding="utf-8")
            (fixture / "package.json").write_text(json.dumps({"scripts": {"test": "node scripts/missing.js"}}), encoding="utf-8")
            (fixture / "expected.json").write_text(json.dumps({
                "must_emit": [{"rule_id": "AET-PKG-001", "status": "FAIL", "evidence_path": "package.json"}]
            }), encoding="utf-8")
            report = root / "audit.json"
            report.write_text(json.dumps({"report_kind": "audit", "findings": [], "summary": {"PASS": 0, "FAIL": 0, "UNKNOWN": 0}}), encoding="utf-8")
            output = root / "feedback.json"
            result = record_audit_feedback(
                report=report, finding="AET-PKG-001", outcome="false-negative",
                reason_code="MISSING_PACKAGE_SCRIPT", fixture=fixture, output=output,
            )
            self.assertTrue(result["adoption_grade"])
            self.assertTrue(result["reproduced"])
            self.assertEqual(result["deviations"], ["FALSE_NEGATIVE", "MISSING_PACKAGE_SCRIPT"])
            self.assertEqual(len(result["fixture_sha256"]), 64)
            self.assertFalse(result["privacy"]["raw_transcript_retained"])

    def test_feedback_without_expected_fixture_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture"
            fixture.mkdir()
            report = root / "audit.json"
            report.write_text(json.dumps({"report_kind": "audit", "findings": []}), encoding="utf-8")
            with self.assertRaises(AuditFeedbackError):
                record_audit_feedback(report=report, finding="AET-X", outcome="false-negative", reason_code="MISSING", fixture=fixture, output=root / "feedback.json")

    def test_false_positive_requires_an_explicit_must_not_emit_expectation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture"
            fixture.mkdir()
            (fixture / "AGENTS.md").write_text("[missing](docs/nope.md)\n", encoding="utf-8")
            (fixture / "expected.json").write_text(json.dumps({"must_emit": [{"rule_id": "AET-CTX-001"}], "must_not_emit": []}), encoding="utf-8")
            report = root / "audit.json"
            report.write_text(json.dumps({"report_kind": "audit", "findings": [{"rule_id": "AET-CTX-001"}]}), encoding="utf-8")
            with self.assertRaises(AuditFeedbackError):
                record_audit_feedback(report=report, finding="AET-CTX-001", outcome="false-positive", reason_code="EXAMPLE_BLOCK", fixture=fixture, output=root / "feedback.json")

    def test_special_feedback_outcomes_require_measurable_fixture_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fixture = root / "fixture"
            fixture.mkdir()
            (fixture / "AGENTS.md").write_text("[missing](docs/nope.md)\n", encoding="utf-8")
            report = root / "audit.json"
            report.write_text(json.dumps({"report_kind": "audit", "findings": [{"rule_id": "AET-CTX-001"}]}), encoding="utf-8")
            expected = {"must_emit": [{"rule_id": "AET-CTX-001"}], "must_not_emit": [], "max_runtime_ms": 0}
            (fixture / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
            performance = record_audit_feedback(report=report, finding="AET-CTX-001", outcome="performance-regression", reason_code="TOO_SLOW", fixture=fixture, output=root / "performance.json")
            self.assertEqual(performance["deviations"][0], "PERFORMANCE_REGRESSION")

            expected["must_not_emit"] = [{"rule_id": "AET-CTX-001", "policy_exception": True}]
            (fixture / "expected.json").write_text(json.dumps(expected), encoding="utf-8")
            exception = record_audit_feedback(report=report, finding="AET-CTX-001", outcome="policy-exception-required", reason_code="APPROVED_EXAMPLE", fixture=fixture, output=root / "exception.json")
            self.assertEqual(exception["deviations"][0], "POLICY_EXCEPTION_REQUIRED")

            first = Finding("AET-CTX-001", Status.FAIL, Severity.ERROR, "one", (Evidence("AGENTS.md"),), "fix", "1")
            second = Finding("AET-CTX-001", Status.FAIL, Severity.ERROR, "two", (Evidence("AGENTS.md"),), "fix", "1")
            with patch("aet.audit_feedback.run_rules", side_effect=[[first], [second]]):
                unstable = record_audit_feedback(report=report, finding="AET-CTX-001", outcome="non-deterministic", reason_code="UNSTABLE_ORDER", fixture=fixture, output=root / "unstable.json")
            self.assertEqual(unstable["deviations"][0], "NON_DETERMINISTIC")


if __name__ == "__main__":
    unittest.main()
