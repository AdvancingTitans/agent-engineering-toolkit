from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aet.improvement.analyzer import aggregate_findings, normalize_finding
from aet.improvement.cli.improve import generate_improvements
from aet.improvement.constraint import build_constraint
from aet.improvement.renderer import render_human_report


ROOT = Path(__file__).resolve().parents[3]
MINIMAL = ROOT / "tests/fixtures/evidence-bundles/minimal"


class DeterministicImprovementEngineTests(unittest.TestCase):
    def test_scope_violation_normalization(self) -> None:
        issue = normalize_finding(
            {
                "id": "FND-001",
                "type": "scope_violation",
                "evidence_refs": ["EV-001"],
            }
        )

        self.assertIsNotNone(issue)
        self.assertEqual(issue.category, "scope_violation")
        self.assertEqual(issue.finding_refs, ["FND-001"])
        self.assertEqual(issue.evidence_refs, ["EV-001"])

    def test_all_planned_categories_normalize(self) -> None:
        categories = [
            "scope_violation",
            "unsupported_claim",
            "missing_verification",
            "stale_verification",
            "missing_test",
            "error_handling_gap",
            "unknown_root_cause",
        ]

        issues = [
            normalize_finding({"id": category, "type": category})
            for category in categories
        ]

        self.assertEqual(
            [item.category for item in issues if item is not None],
            categories,
        )

    def test_unknown_requires_investigation(self) -> None:
        issue = normalize_finding(
            {
                "id": "FND-UNKNOWN",
                "root_cause_status": "unknown",
                "status": "unknown",
            }
        )

        self.assertIsNotNone(issue)
        constraint = build_constraint(issue)
        self.assertEqual(constraint.action, "investigate")
        self.assertNotIn("src/auth.py", " ".join(constraint.required_behavior))

    def test_human_report_contains_every_required_section(self) -> None:
        issue = normalize_finding(
            {
                "id": "FND-001",
                "type": "unsupported_claim",
                "statement": "An empty tool result became a factual claim.",
                "evidence_refs": ["EV-001"],
            }
        )

        self.assertIsNotNone(issue)
        constraint = build_constraint(
            issue,
            allowed_paths=["src/tool/result.py"],
            verification_requirements=["python -m unittest tests.test_tool"],
        )
        report = render_human_report(issue, constraint)

        for heading in (
            "一句话结论",
            "为什么发现",
            "证据",
            "影响",
            "建议目标",
            "禁止修改",
            "验证方式",
            "未知项",
        ):
            self.assertIn(f"### {heading}", report)

    def test_aggregation_is_bounded_and_stable(self) -> None:
        findings = [
            {
                "id": f"FND-{number}",
                "type": "missing_test",
                "component": f"component-{number}",
            }
            for number in range(8)
        ]

        first = aggregate_findings(findings)
        second = aggregate_findings(reversed(findings))

        self.assertEqual(first, second)
        self.assertEqual(len(first), 5)
        self.assertEqual([item.id for item in first], [f"IMP-{n:03d}" for n in range(1, 6)])

    def test_same_bundle_produces_same_report_hash_ten_times(self) -> None:
        hashes: set[str] = set()
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            for number in range(10):
                output = root / str(number)
                generate_improvements(MINIMAL, output=output)
                hashes.add(
                    hashlib.sha256(
                        (output / "human-report.md").read_bytes()
                    ).hexdigest()
                )

        self.assertEqual(len(hashes), 1)

    def test_supported_bundle_has_no_actionable_issue(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            output = Path(raw) / "improvements"
            result = generate_improvements(MINIMAL, output=output)

            self.assertEqual(result["issue_count"], 0)
            self.assertEqual(
                json.loads((output / "issues.json").read_text(encoding="utf-8")),
                [],
            )
            self.assertIn(
                "No actionable improvements",
                (output / "human-report.md").read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
