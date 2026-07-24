from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from types import SimpleNamespace
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "eval" / "quick-investigation"
SUITE = BENCHMARK / "fixtures" / "scope-scenarios.json"


def load_script(name: str) -> ModuleType:
    path = BENCHMARK / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"aet_test_quick_{name}", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


RUNNER = load_script("runner")
SCORER = load_script("scorer")


class QuickBenchmarkContractTests(unittest.TestCase):
    def test_suite_fixes_four_groups_and_eight_scope_categories(self) -> None:
        suite = RUNNER.load_suite(SUITE)
        self.assertEqual(
            (
                "pure_rules",
                "one_shot_llm",
                "investigated_aet",
                "investigated_grounded",
            ),
            RUNNER.GROUPS,
        )
        self.assertEqual(list(RUNNER.GROUPS), suite["groups"])
        self.assertEqual(list(RUNNER.CLAIM_CATALOG), suite["claim_catalog"])
        self.assertEqual(8, len(suite["scenarios"]))
        self.assertEqual(list(RUNNER.CATEGORIES), [item["category"] for item in suite["scenarios"]])

    def test_tracked_json_contracts_parse_and_use_draft_2020_12(self) -> None:
        for path in sorted((BENCHMARK / "schemas").glob("*.json")):
            with self.subTest(path=path.name):
                schema = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual("https://json-schema.org/draft/2020-12/schema", schema["$schema"])
        example = json.loads((BENCHMARK / "annotations.example.json").read_text(encoding="utf-8"))
        self.assertEqual("quick-investigation-annotations/v1", example["schema_version"])

    def test_published_v113_result_binds_real_grounded_comparison(self) -> None:
        result = json.loads(
            (BENCHMARK / "results" / "v1.13.0.json").read_text(encoding="utf-8")
        )
        self.assertEqual("quick-investigation-published-result/v1", result["schema_version"])
        self.assertEqual(64, result["method"]["total_runs"])
        self.assertTrue(result["method"]["grounded_group_uses_shipped_validator"])
        self.assertTrue(result["method"]["grounded_group_uses_distinct_prompt"])
        self.assertEqual("fixture_synthesized", result["method"]["grounding_ledger_source"])
        self.assertEqual(set(RUNNER.GROUPS), set(result["groups"]))
        self.assertEqual("UNKNOWN", result["human_metrics"]["manual_review_seconds"])
        bundle = BENCHMARK / "results" / "v1.13.0-normalized-runs.json"
        report = SCORER.score(SUITE, bundle)
        self.assertEqual(64, len(report["runs"]))
        for group, published in result["groups"].items():
            rescored = report["groups"][group]
            self.assertEqual(
                published["effective_recall"],
                rescored["effective_recall"]["rate"],
            )
            self.assertEqual(
                published["false_discovery_proportion"],
                rescored["false_discovery_proportion"]["rate"],
            )

    def test_codex_jsonl_collects_usage_and_deduplicated_completed_tools(self) -> None:
        rows = [
            {"type": "item.started", "item": {"id": "a", "type": "command_execution"}},
            {"type": "item.completed", "item": {"id": "a", "type": "command_execution"}},
            {"type": "item.completed", "item": {"id": "a", "type": "command_execution"}},
            {"type": "item.completed", "item": {"id": "b", "type": "mcp_tool_call"}},
            {"type": "item.completed", "item": {"id": "m", "type": "agent_message", "text": "{}"}},
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 120,
                    "output_tokens": 30,
                    "reasoning_output_tokens": 11,
                },
            },
        ]
        parsed = RUNNER.parse_codex_jsonl(
            "not json\n" + "".join(json.dumps(row) + "\n" for row in rows)
        )
        self.assertEqual(2, parsed["tool_calls"])
        self.assertEqual("{}", parsed["final_text"])
        self.assertEqual(
            {
                "status": "EVIDENCED",
                "input_tokens": 120,
                "output_tokens": 30,
                "reasoning_tokens": 11,
                "total_tokens": 150,
            },
            parsed["usage"],
        )
        self.assertEqual("UNKNOWN", RUNNER.parse_codex_jsonl("{}\n")["usage"]["status"])

    def test_output_parser_fails_closed_and_accepts_fenced_json(self) -> None:
        self.assertEqual("UNKNOWN", RUNNER.parse_output("A plausible answer")["status"])
        value = {
            "schema_version": "quick-investigation-output/v1",
            "status": "COMPLETE",
            "claims": [{
                "claim_id": "scope_expansion",
                "assessment_state": "OUT_OF_SCOPE",
                "evidence_refs": ["intent", "diff", "intent"],
            }],
        }
        parsed = RUNNER.parse_output(f"```json\n{json.dumps(value)}\n```")
        self.assertEqual("COMPLETE", parsed["status"])
        self.assertEqual(["intent", "diff"], parsed["claims"][0]["evidence_refs"])

    def test_repeated_pure_rule_runs_remain_zero_model_baseline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "runs"
            runs = RUNNER.run_benchmark(
                SUITE,
                output,
                ("pure_rules",),
                repetitions=2,
                model="ignored-for-deterministic-baseline",
                model_parameters={"model_reasoning_effort": "medium"},
            )
            self.assertEqual(16, len(runs))
            self.assertTrue(all(run["runner"] == "deterministic" for run in runs))
            self.assertTrue(all(run["model"] is None for run in runs))
            self.assertTrue(all(run["model_parameters"] == {} for run in runs))
            self.assertEqual(16, len(list(output.rglob("run.json"))))

    def test_same_model_and_parameters_are_bound_to_repeated_codex_runs(self) -> None:
        response = {
            "schema_version": "quick-investigation-output/v1",
            "status": "COMPLETE",
            "claims": [],
        }
        stdout = "".join([
            json.dumps({
                "type": "item.completed",
                "item": {"id": "m", "type": "agent_message", "text": json.dumps(response)},
            }) + "\n",
            json.dumps({
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 10,
                    "output_tokens": 2,
                    "reasoning_output_tokens": 1,
                },
            }) + "\n",
        ])
        with tempfile.TemporaryDirectory() as temporary, patch.object(
            RUNNER.subprocess,
            "run",
            return_value=SimpleNamespace(stdout=stdout, stderr="", returncode=0),
        ) as mocked:
            runs = RUNNER.run_benchmark(
                SUITE,
                Path(temporary) / "runs",
                ("one_shot_llm",),
                repetitions=2,
                model="gpt-test",
                model_parameters={"model_reasoning_effort": "medium"},
            )
            self.assertEqual(16, len(runs))
            self.assertEqual(16, mocked.call_count)
            self.assertTrue(all(run["model"] == "gpt-test" for run in runs))
            self.assertTrue(all(
                run["model_parameters"] == {"model_reasoning_effort": "medium"}
                for run in runs
            ))
            self.assertTrue(all(run["usage"]["reasoning_tokens"] == 1 for run in runs))
            self.assertTrue(all(run["usage"]["status"] == "EVIDENCED" for run in runs))

    def test_codex_argv_binds_one_model_and_canonical_parameters(self) -> None:
        argv = RUNNER._codex_argv(
            "codex",
            "gpt-5",
            {"temperature": 0, "model_reasoning_effort": "medium"},
            Path("/tmp/workspace"),
            Path("/tmp/final.txt"),
        )
        self.assertEqual("gpt-5", argv[argv.index("--model") + 1])
        configs = [argv[index + 1] for index, item in enumerate(argv) if item == "-c"]
        self.assertEqual(
            ['model_reasoning_effort="medium"', "temperature=0"],
            configs,
        )
        self.assertIn("read-only", argv)

    def test_scorer_reports_metrics_and_preserves_missing_human_data(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runs_root = root / "runs"
            RUNNER.run_benchmark(
                SUITE,
                runs_root,
                ("pure_rules",),
                repetitions=1,
                model=None,
                model_parameters={},
            )
            report = SCORER.score(SUITE, runs_root)
            metrics = report["groups"]["pure_rules"]
            self.assertEqual(5, metrics["effective_recall"]["expected_claims"])
            self.assertEqual(3, metrics["effective_recall"]["true_positive_claims"])
            self.assertEqual(3, metrics["false_discovery_proportion"]["count"])
            self.assertEqual(0, metrics["ungrounded_conclusions"]["count"])
            self.assertEqual(0, metrics["tokens"]["total_tokens"]["total"])
            self.assertEqual("EVIDENCED", metrics["tokens"]["total_tokens"]["status"])
            self.assertEqual("UNKNOWN", metrics["manual_review_seconds"]["status"])
            self.assertEqual("UNKNOWN", metrics["user_understanding"]["status"])
            self.assertTrue(all(item["manual_review_seconds"]["status"] == "UNKNOWN" for item in report["runs"]))

            annotations = root / "annotations.json"
            annotations.write_text(json.dumps({
                "schema_version": "quick-investigation-annotations/v1",
                "annotations": [{
                    "run_id": "pure_rules-SCOPE-001-000",
                    "manual_review_seconds": 12.5,
                    "user_understanding": "CORRECT",
                }],
            }), encoding="utf-8")
            annotated = SCORER.score(SUITE, runs_root, annotations)
            annotated_metrics = annotated["groups"]["pure_rules"]
            self.assertEqual("EVIDENCED", annotated_metrics["manual_review_seconds"]["status"])
            self.assertEqual(12.5, annotated_metrics["manual_review_seconds"]["value"]["mean"])
            self.assertEqual(
                {"CORRECT": 1, "PARTIAL": 0, "INCORRECT": 0},
                annotated_metrics["user_understanding"]["value"],
            )
            unknown = [
                item for item in annotated["runs"]
                if item["run_id"] == "pure_rules-SCOPE-002-000"
            ][0]
            self.assertEqual("UNKNOWN", unknown["manual_review_seconds"]["status"])

    def test_scorer_marks_missing_or_unknown_evidence_as_ungrounded(self) -> None:
        suite = RUNNER.load_suite(SUITE)
        scenario = suite["scenarios"][0]
        run = {
            "run_id": "test-run",
            "group": "investigated_grounded",
            "scenario_id": scenario["scenario_id"],
            "output": {
                "claims": [
                    {
                        "claim_id": "scope_expansion",
                        "assessment_state": "OUT_OF_SCOPE",
                        "evidence_refs": ["invented"],
                    },
                    {
                        "claim_id": "unrelated_dependency",
                        "assessment_state": "OUT_OF_SCOPE",
                        "evidence_refs": [],
                    },
                ]
            },
        }
        result = SCORER.score_run(run, scenario, None)
        self.assertEqual(
            ["scope_expansion", "unrelated_dependency"],
            result["ungrounded_claim_ids"],
        )

    def test_grounded_group_uses_shipped_validator_and_rejects_missing_counter(self) -> None:
        suite = RUNNER.load_suite(SUITE)
        scenario = suite["scenarios"][0]
        output = {
            "schema_version": "quick-investigation-output/v1",
            "status": "COMPLETE",
            "claims": [{
                "claim_id": "scope_expansion",
                "assessment_state": "SUPPORTED",
                "evidence_refs": ["intent", "diff"],
            }],
        }
        grounded, result = RUNNER.apply_grounding(output, scenario)
        self.assertEqual([], grounded["claims"])
        self.assertEqual("REJECTED", result["status"])
        accepted, accepted_result = RUNNER.apply_grounding(
            {
                "schema_version": "quick-investigation-output/v1",
                "status": "COMPLETE",
                "claims": [{
                    "claim_id": "scope_expansion",
                    "assessment_state": "SUPPORTED",
                    "evidence_refs": ["intent", "diff"],
                    "counter_explanation": "The payment edit may be required by a shared interface.",
                    "counter_evidence_refs": ["dependency"],
                    "remaining_uncertainty": [],
                }],
            },
            scenario,
        )
        self.assertEqual(1, len(accepted["claims"]))
        self.assertEqual("PASS", accepted_result["status"])


if __name__ == "__main__":
    unittest.main()
