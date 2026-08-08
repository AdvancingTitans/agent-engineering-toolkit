from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "eval/behavioural-risk"
CORPUS = EVAL / "public-corpus.json"


def _runner_module():
    previous_scorer = sys.modules.get("scorer")
    sys.path.insert(0, str(EVAL))
    try:
        spec = importlib.util.spec_from_file_location("aet_risk_eval_runner", EVAL / "runner.py")
        if spec is None or spec.loader is None:
            raise RuntimeError("cannot load behavioural-risk evaluation runner")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.remove(str(EVAL))
        if previous_scorer is None:
            sys.modules.pop("scorer", None)
        else:
            sys.modules["scorer"] = previous_scorer


class PublicBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.runner = _runner_module()

    def test_pinned_agentdojo_corpus_is_a_diagnosis_only_release_gate(self) -> None:
        report = self.runner.run_public_benchmark(CORPUS)
        self.assertEqual(report["status"], "PASS")
        self.assertEqual(report["release_scope"], "diagnosis_only")
        self.assertEqual(report["metrics"]["case_count"], 9)
        self.assertEqual(report["metrics"]["exact_case_accuracy"], 1.0)
        self.assertEqual(report["metrics"]["cited_failure_coverage"], 1.0)
        self.assertEqual(report["source"]["commit"], "089ed468cf3ed0322acc66b0211f26d9d90dbf60")
        self.assertFalse(report["human_validation_claimed"])
        self.assertFalse(report["forecast_eligible"])
        self.assertFalse(report["network_used"])
        self.assertFalse(report["model_used"])

    def test_upstream_label_and_derived_expected_label_cannot_be_silently_changed(self) -> None:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        unsafe = next(case for case in corpus["cases"] if case["variant"] == "unsafe")
        unsafe["upstream_labels"]["security"] = False
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "corpus.json"
            path.write_text(json.dumps(corpus), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "unsafe public corpus case"):
                self.runner.run_public_benchmark(path)

        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        unsafe = next(case for case in corpus["cases"] if case["variant"] == "unsafe")
        unsafe["expected"]["goal_divergence_indicator"] = "PASS"
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "corpus.json"
            path.write_text(json.dumps(corpus), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "expected labels are not derivable"):
                self.runner.run_public_benchmark(path)

    def test_corpus_retains_only_hash_bound_decision_events(self) -> None:
        corpus = json.loads(CORPUS.read_text(encoding="utf-8"))
        serialized = json.dumps(corpus, sort_keys=True)
        self.assertNotIn('"prompt"', serialized)
        self.assertNotIn('"content"', serialized)
        for case in corpus["cases"]:
            self.assertEqual(len(case["upstream_sha256"]), 64)
            for event in case["events"]:
                self.assertEqual(len(event["arguments_sha256"]), 64)
                self.assertEqual(len(event["effect_sha256"]), 64)


if __name__ == "__main__":
    unittest.main()
