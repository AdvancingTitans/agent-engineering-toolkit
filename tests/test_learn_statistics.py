from __future__ import annotations

import unittest

from aet.learn_statistics import compare_pairs, summarize_reliability


def pair(task: str, baseline: str, candidate: str, *, candidate_findings: list[dict] | None = None) -> dict:
    return {
        "task_id": task,
        "baseline": {"status": baseline, "findings": []},
        "candidate": {"status": candidate, "findings": candidate_findings or []},
    }


class ReliabilityStatisticsTests(unittest.TestCase):
    def test_empty_observations_are_unknown(self) -> None:
        self.assertEqual({"status": "UNKNOWN", "groups": []}, summarize_reliability([]))

    def test_zero_of_five_and_five_of_five_report_wilson_intervals(self) -> None:
        rows = [pair("zero", "FAIL", "FAIL") for _ in range(5)] + [pair("all", "FAIL", "PASS") for _ in range(5)]
        groups = {(row["task_id"], row["variant"]): row for row in summarize_reliability(rows)["groups"]}
        zero = groups[("zero", "candidate")]
        all_success = groups[("all", "candidate")]
        self.assertEqual((0, 5, False, False), (zero["successes"], zero["runs"], zero["any_success"], zero["all_success"]))
        self.assertAlmostEqual(0.0, zero["wilson_95"]["lower"], places=6)
        self.assertAlmostEqual(0.434482, zero["wilson_95"]["upper"], places=6)
        self.assertEqual((5, 5, True, True), (all_success["successes"], all_success["runs"], all_success["any_success"], all_success["all_success"]))
        self.assertAlmostEqual(0.565518, all_success["wilson_95"]["lower"], places=6)
        self.assertAlmostEqual(1.0, all_success["wilson_95"]["upper"], places=6)

    def test_six_of_six_is_grouped_by_task_and_variant(self) -> None:
        rows = [pair("stable", "PASS", "PASS") for _ in range(6)]
        report = compare_pairs(rows, profile="preliminary")
        candidate = next(row for row in report["reliability"]["groups"] if row["task_id"] == "stable" and row["variant"] == "candidate")
        self.assertEqual((6, 6, True, True), (candidate["successes"], candidate["runs"], candidate["any_success"], candidate["all_success"]))

    def test_four_better_two_worse_keeps_exact_mcnemar_gate(self) -> None:
        rows = [pair("task", "FAIL", "PASS") for _ in range(4)] + [pair("task", "PASS", "FAIL") for _ in range(2)]
        report = compare_pairs(rows, profile="adoptable")
        self.assertEqual((4, 2), (report["better"], report["worse"]))
        self.assertAlmostEqual(0.6875, report["mcnemar_exact_p_value"])
        self.assertEqual("INCONCLUSIVE", report["status"])

    def test_infrastructure_pair_remains_infrastructure_error(self) -> None:
        report = compare_pairs([pair("task", "PASS", "INFRASTRUCTURE_ERROR")], profile="adoptable")
        self.assertEqual("INFRASTRUCTURE_ERROR", report["status"])
        groups = {(row["task_id"], row["variant"]): row for row in report["reliability"]["groups"]}
        self.assertEqual((1, "PASS"), (groups[("task", "baseline")]["runs"], groups[("task", "baseline")]["status"]))
        self.assertEqual((0, "UNKNOWN"), (groups[("task", "candidate")]["runs"], groups[("task", "candidate")]["status"]))
        self.assertNotIn("wilson_95", groups[("task", "candidate")])

    def test_exact_mcnemar_five_improvements_are_inconclusive_but_six_pass(self) -> None:
        five = compare_pairs([pair("task", "FAIL", "PASS") for _ in range(5)], profile="adoptable")
        six = compare_pairs([pair("task", "FAIL", "PASS") for _ in range(6)], profile="adoptable")
        self.assertEqual((0.0625, "INCONCLUSIVE"), (five["mcnemar_exact_p_value"], five["status"]))
        self.assertEqual((0.03125, "PASS"), (six["mcnemar_exact_p_value"], six["status"]))

    def test_new_declared_safety_failure_is_a_hard_regression(self) -> None:
        finding = {"code": "TOOL_CALL_ARGUMENT_MISMATCH", "status": "FAIL"}
        report = compare_pairs([pair("task", "PASS", "FAIL", candidate_findings=[finding])], profile="preliminary")
        self.assertEqual(["TOOL_CALL_ARGUMENT_MISMATCH"], report["hard_regressions"])
        self.assertEqual("FAIL", report["status"])


if __name__ == "__main__":
    unittest.main()
