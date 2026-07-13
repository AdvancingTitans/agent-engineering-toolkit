from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "schemas" / "audit-task-v1.schema.json"
SUITES = ROOT / "tests" / "evolution" / "audit"
EXPECTED_COUNTS = {"core": 30, "validation": 15, "held_out": 15, "adversarial": 10}
REQUIRED_QUALITY = {
    "true_positive",
    "false_positive",
    "false_negative",
    "evidence_location_accuracy",
    "status_accuracy",
    "severity_accuracy",
    "remediation_presence",
    "determinism",
    "runtime",
}


class AuditEvolutionSuiteTests(unittest.TestCase):
    def test_schema_and_partitioned_suites_are_complete(self) -> None:
        seen: set[str] = set()
        covered_quality: set[str] = set()
        covered_rules: set[str] = set()

        for partition, expected_count in EXPECTED_COUNTS.items():
            path = SUITES / partition / "suite.json"
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["schema_version"], "audit-task/v1")
            self.assertEqual(payload["partition"], partition)
            self.assertEqual(len(payload["tasks"]), expected_count)
            defaults = payload["defaults"]
            for task in payload["tasks"]:
                task_id = task["task_id"]
                self.assertNotIn(task_id, seen)
                seen.add(task_id)
                fixture = ROOT / task["fixture"]["source"]
                self.assertTrue(fixture.is_dir(), f"missing fixture for {task_id}: {fixture}")
                self.assertEqual(defaults["command"]["argv"][:2], ["aet", "audit"])
                self.assertIn("must_emit", task["expected"])
                self.assertIn("must_not_emit", task["expected"])
                self.assertTrue(defaults["quality"]["require_deterministic_output"])
                self.assertGreater(defaults["quality"]["max_runtime_ms"], 0)
                covered_quality.update(task["dimensions"])
                covered_rules.update(item["rule_id"] for item in task["expected"]["must_emit"])

        self.assertEqual(len(seen), sum(EXPECTED_COUNTS.values()))
        self.assertTrue(REQUIRED_QUALITY <= covered_quality)
        self.assertTrue(
            {"AET-GEN-001", "AET-CTX-001", "AET-CTX-002", "AET-CTX-003", "AET-CTX-004", "AET-CTX-005", "AET-SKL-001", "AET-SKL-002", "AET-SKL-004", "AET-PKG-001"}
            <= covered_rules
        )
        self.assertTrue(SCHEMA.is_file(), "audit-task/v1 schema has not been implemented")

    def test_adversarial_suite_exercises_constitution(self) -> None:
        payload = json.loads((SUITES / "adversarial" / "suite.json").read_text(encoding="utf-8"))
        principles = {tag for task in payload["tasks"] for tag in task["tags"] if tag.startswith("constitution:")}
        self.assertEqual(
            principles,
            {
                "constitution:unknown-is-not-pass",
                "constitution:evidence-required",
                "constitution:evaluator-immutable",
                "constitution:held-out-separate",
                "constitution:human-adoption",
                "constitution:baseline-hash",
                "constitution:no-hard-failure-reduction",
                "constitution:shadow-exit-code-isolated",
            },
        )


if __name__ == "__main__":
    unittest.main()
