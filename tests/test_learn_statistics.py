from __future__ import annotations

import unittest

from aet.learn_statistics import alpha_spending_schedule, compare_pairs, sequential_decision, summarize_reliability


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

    def test_core_no_regression_accepts_stable_passes(self) -> None:
        report = compare_pairs(
            [pair("core", "PASS", "PASS") for _ in range(4)],
            profile="adoptable",
            objective="no_regression",
            minimum_pairs=4,
        )
        self.assertEqual("PASS", report["status"])
        self.assertEqual("no_regression", report["objective"])

    def test_sequential_success_uses_prespecified_look_alpha(self) -> None:
        rows = [pair("task", "FAIL", "PASS") for _ in range(8)]
        report = sequential_decision(
            rows,
            objective="superiority",
            minimum_pairs=4,
            maximum_pairs=12,
            batch_size=2,
            alpha=0.05,
            mcid=0.05,
        )
        self.assertEqual("PASS", report["status"])
        self.assertEqual("SUCCESS_BOUNDARY", report["stop_reason"])
        self.assertAlmostEqual(0.05 / 6, report["look_alpha"])

    def test_directional_objective_uses_one_sided_exact_test(self) -> None:
        report = compare_pairs([pair("task", "FAIL", "PASS") for _ in range(5)], profile="adoptable", objective="superiority", minimum_pairs=5)
        self.assertAlmostEqual(0.03125, report["directional_mcnemar_p_value"])
        self.assertEqual("PASS", report["status"])

    def test_contract_retention_rejects_both_variants_failing(self) -> None:
        report = compare_pairs([pair("core", "FAIL", "FAIL") for _ in range(4)], profile="adoptable", objective="no_regression", minimum_pairs=4)
        self.assertEqual("FAIL", report["status"])

    def test_directional_regression_is_fail_not_inconclusive(self) -> None:
        report = compare_pairs([pair("task", "PASS", "FAIL")], profile="adoptable", objective="superiority", minimum_pairs=1)
        self.assertEqual("FAIL", report["status"])

    def test_alpha_spending_is_bounded_by_family_alpha(self) -> None:
        schedule = alpha_spending_schedule(maximum_pairs=12, batch_size=2, alpha=0.05)
        self.assertEqual(6, len(schedule))
        self.assertAlmostEqual(0.05, sum(row["local_alpha"] for row in schedule))
        self.assertAlmostEqual(0.05, schedule[-1]["cumulative_alpha"])

    def test_futility_stops_only_when_even_all_remaining_improvements_cannot_pass(self) -> None:
        report = sequential_decision([pair("task", "PASS", "PASS") for _ in range(4)], objective="superiority", minimum_pairs=4, maximum_pairs=6, batch_size=2, alpha=0.05, mcid=0.05)
        self.assertEqual(("INCONCLUSIVE", "FUTILITY_BOUNDARY"), (report["status"], report["stop_reason"]))

    def test_sequential_fixed_sample_p_value_cannot_be_peeked_into_pass(self) -> None:
        rows = [pair("task", "FAIL", "PASS") for _ in range(6)]
        legacy = compare_pairs(rows, profile="adoptable")
        sequential = sequential_decision(rows, objective="superiority", minimum_pairs=4, maximum_pairs=12, batch_size=2, alpha=0.05, mcid=0.05)
        self.assertEqual("PASS", legacy["status"])
        self.assertEqual("CONTINUE", sequential["status"])
        self.assertEqual("EVIDENCE_PENDING", sequential["stop_reason"])

    def test_sequential_hard_regression_stops_immediately(self) -> None:
        finding = {"code": "TOOL_CALL_ARGUMENT_MISMATCH", "status": "FAIL"}
        report = sequential_decision([pair("task", "PASS", "FAIL", candidate_findings=[finding])], objective="superiority", minimum_pairs=4, maximum_pairs=12, batch_size=2, alpha=0.05, mcid=0.05)
        self.assertEqual(("FAIL", "HARD_REGRESSION"), (report["status"], report["stop_reason"]))


if __name__ == "__main__":
    unittest.main()
