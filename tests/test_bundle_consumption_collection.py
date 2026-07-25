from __future__ import annotations

import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "eval" / "bundle-consumption"
CATALOG = (
    ROOT / "eval" / "investigation-quality" / "fixtures" / "scenarios.json"
)
PUBLISHED_RESULT = EVAL / "results" / "v1.14.0.json"
sys.path.insert(0, str(EVAL))


def _load(name: str, path: Path) -> ModuleType:
    specification = importlib.util.spec_from_file_location(name, path)
    if specification is None or specification.loader is None:
        raise AssertionError(f"无法加载 {path}")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


class BundleConsumptionCollectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.generator = _load("fixture_generator", EVAL / "generate_fixtures.py")
        cls.prompt = _load("prompt_renderer", EVAL / "prepare_prompt.py")
        cls.base_scorer = _load("base_scorer", EVAL / "scorer.py")
        cls.scorer = _load("collection_scorer", EVAL / "score_collection.py")
        cls.collector = _load("consumer_collector", EVAL / "collect_consumer.py")
        cls.publisher = _load(
            "collection_publisher",
            EVAL / "publish_collection.py",
        )
        cls.local_schema = _load(
            "local_structured_consumer",
            EVAL / "ollama_structured_consumer.py",
        )

    def test_prompt_is_deterministic_and_sdk_free(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundles = Path(temporary) / "bundles"
            self.generator.generate_fixtures(bundles)
            first = self.prompt.build_prompt(CATALOG, bundles)
            second = self.prompt.build_prompt(CATALOG, bundles)
            self.assertEqual(first, second)
            for scenario_id in self.generator.SCENARIO_IDS:
                self.assertIn(f'"scenario_id":"{scenario_id}"', first)
            self.assertIn("No SDK or AET runtime is available", first)

    def test_unavailable_consumer_remains_not_applicable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundles = Path(temporary) / "bundles"
            self.generator.generate_fixtures(bundles)
            report = self.scorer.score_collection(
                CATALOG,
                bundles,
                None,
                consumer_id="unavailable-consumer",
                consumer_available=False,
                elapsed_seconds=None,
            )
            self.assertIsNone(report["aggregate_score"])
            self.assertEqual("NOT_APPLICABLE", report["consumer_status"])
            self.assertEqual(
                {"NOT_APPLICABLE"},
                {
                    scenario["consumer_status"]
                    for scenario in report["scenarios"]
                },
            )

    def test_collection_requires_exact_scenario_closure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundles = Path(temporary) / "bundles"
            self.generator.generate_fixtures(bundles)
            with self.assertRaises(ValueError):
                self.scorer.score_collection(
                    CATALOG,
                    bundles,
                    {"reviews": []},
                    consumer_id="incomplete-consumer",
                    consumer_available=True,
                    elapsed_seconds=1.0,
                )

    def test_failure_rates_and_bundle_identity_fail_closed(self) -> None:
        fixture = ROOT / "tests" / "fixtures" / "evidence-bundles" / "minimal"
        review = json.loads(
            (EVAL / "fixtures" / "minimal-review.json").read_text(encoding="utf-8")
        )
        report = self.base_scorer.evaluate(
            fixture,
            review,
            scenario_id="minimal",
            consumer_id="fixture",
            expected_relevant_evidence_refs=["ev-001"],
        )
        self.assertEqual(
            0.0,
            report["metrics"]["unsupported_conclusion_rate"]["rate"],
        )
        review["bundle_id"] = "wrong-bundle"
        with self.assertRaises(ValueError):
            self.base_scorer.evaluate(
                fixture,
                review,
                scenario_id="minimal",
                consumer_id="fixture",
            )

    def test_collector_requires_strict_unique_json_object(self) -> None:
        self.assertEqual(
            {"reviews": []},
            self.collector._strict_object('{"reviews":[]}'),
        )
        for invalid in (
            "[]",
            '{"reviews":[],"reviews":[]}',
            '{"reviews":NaN}',
        ):
            with self.subTest(invalid=invalid):
                with self.assertRaises(ValueError):
                    self.collector._strict_object(invalid)

    def test_local_consumer_schema_requires_ten_reviews(self) -> None:
        reviews = self.local_schema.REVIEW_SCHEMA["properties"]["reviews"]
        self.assertEqual(10, reviews["minItems"])
        self.assertEqual(10, reviews["maxItems"])
        disposition = (
            reviews["items"]["properties"]["review"]["properties"]["conclusions"][
                "items"
            ]["properties"]["disposition"]["enum"]
        )
        self.assertNotIn("supported", disposition)

    def test_published_result_preserves_independent_metric_boundaries(self) -> None:
        result = json.loads(PUBLISHED_RESULT.read_text(encoding="utf-8"))
        self.assertIsNone(result["method"]["aggregate_score"])
        self.assertFalse(result["fixture_suite"]["general_accuracy_claim"])
        available = [
            item for item in result["consumers"] if item["status"] == "AVAILABLE"
        ]
        self.assertEqual(3, len(available))
        for consumer in available:
            with self.subTest(consumer=consumer["id"]):
                self.assertTrue(consumer["strict_json"])
                self.assertEqual(10, consumer["scenario_count"])
                self.assertEqual(
                    {"PASS": 62, "FAIL": 0, "UNKNOWN": 0},
                    consumer["applicable_metric_statuses"],
                )
        unavailable = [
            item
            for item in result["consumers"]
            if item["status"] == "NOT_APPLICABLE"
        ]
        self.assertEqual(
            ["claude-code-unavailable"],
            [item["id"] for item in unavailable],
        )

    def test_published_collections_are_hash_bound_and_rescorable(self) -> None:
        summary = json.loads(PUBLISHED_RESULT.read_text(encoding="utf-8"))
        published = {
            item["id"]: item
            for item in summary["consumers"]
            if item["status"] == "AVAILABLE"
        }
        with tempfile.TemporaryDirectory() as temporary:
            bundles = Path(temporary) / "bundles"
            self.generator.generate_fixtures(bundles)
            for consumer in published.values():
                artifact = EVAL / consumer["published_artifacts"]["path"]
                integrity_path = artifact / "integrity.json"
                self.assertEqual(
                    consumer["published_artifacts"]["integrity_sha256"],
                    hashlib.sha256(integrity_path.read_bytes()).hexdigest(),
                )
                integrity = json.loads(integrity_path.read_text(encoding="utf-8"))
                for name, expected in integrity["file_hashes"].items():
                    self.assertEqual(
                        expected,
                        hashlib.sha256((artifact / name).read_bytes()).hexdigest(),
                    )
                response = json.loads(
                    (artifact / "response.json").read_text(encoding="utf-8")
                )
                metadata = json.loads(
                    (artifact / "metadata.json").read_text(encoding="utf-8")
                )
                report = json.loads(
                    (artifact / "report.json").read_text(encoding="utf-8")
                )
                rebuilt = self.scorer.score_collection(
                    CATALOG,
                    bundles,
                    response,
                    consumer_id=metadata["consumer_id"],
                    consumer_available=True,
                    elapsed_seconds=metadata[
                        "elapsed_seconds_to_complete_response"
                    ],
                )
                self.assertEqual(report, rebuilt)
                self.assertTrue(metadata["runtime_version"])
                self.assertTrue(metadata["model_id"])
                self.assertEqual(64, len(metadata["command_argv_sha256"]))

    def test_publisher_uses_only_collection_bound_provenance(self) -> None:
        artifact = EVAL / "results" / "v1.14.0-artifacts" / "hermes-v2"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            bundles = root / "bundles"
            output = root / "published"
            source.mkdir()
            for name in ("response.json", "report.json", "metadata.json"):
                shutil.copyfile(artifact / name, source / name)
            self.generator.generate_fixtures(bundles)
            source_metadata = json.loads(
                (source / "metadata.json").read_text(encoding="utf-8")
            )
            self.publisher.publish_collection(
                source,
                output,
                CATALOG,
                bundles,
            )
            published_metadata = json.loads(
                (output / "metadata.json").read_text(encoding="utf-8")
            )
            for name in (
                "runtime_version",
                "model_id",
                "command_argv_sha256",
            ):
                self.assertEqual(source_metadata[name], published_metadata[name])
            with self.assertRaises(TypeError):
                self.publisher.publish_collection(
                    source,
                    root / "forged",
                    CATALOG,
                    bundles,
                    runtime_version="FORGED RUNTIME",
                )

    def test_publisher_rejects_missing_or_placeholder_provenance(self) -> None:
        artifact = EVAL / "results" / "v1.14.0-artifacts" / "hermes-v2"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundles = root / "bundles"
            self.generator.generate_fixtures(bundles)
            original = json.loads(
                (artifact / "metadata.json").read_text(encoding="utf-8")
            )
            for field, replacement in (
                ("runtime_version", None),
                ("model_id", ""),
                ("command_argv_sha256", "0" * 64),
            ):
                source = root / f"source-{field}"
                source.mkdir()
                for name in ("response.json", "report.json"):
                    shutil.copyfile(artifact / name, source / name)
                metadata = {**original, field: replacement}
                (source / "metadata.json").write_text(
                    json.dumps(metadata),
                    encoding="utf-8",
                )
                with self.subTest(field=field):
                    with self.assertRaises(ValueError):
                        self.publisher.publish_collection(
                            source,
                            root / f"published-{field}",
                            CATALOG,
                            bundles,
                        )


if __name__ == "__main__":
    unittest.main()
