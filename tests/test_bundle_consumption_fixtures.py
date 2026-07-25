from __future__ import annotations

import importlib.util
import json
import re
import tempfile
import unittest
from pathlib import Path
from types import ModuleType
from typing import Any

from aet.bundle import validate_bundle


ROOT = Path(__file__).resolve().parents[1]
GENERATOR = (
    ROOT / "eval" / "bundle-consumption" / "generate_fixtures.py"
)
SCENARIOS = (
    ROOT
    / "eval"
    / "investigation-quality"
    / "fixtures"
    / "scenarios.json"
)


def _load_generator() -> ModuleType:
    specification = importlib.util.spec_from_file_location(
        "bundle_consumption_fixture_generator",
        GENERATOR,
    )
    if specification is None or specification.loader is None:
        raise AssertionError("无法加载 Bundle Fixture 生成器")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class BundleConsumptionFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.generator = _load_generator()

    def test_generates_exactly_ten_valid_synthetic_bundles(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundles"
            generated = self.generator.generate_fixtures(output)

            self.assertEqual(10, len(generated))
            self.assertEqual(
                set(self.generator.SCENARIO_IDS),
                {path.name for path in output.iterdir()},
            )
            bundles = {
                scenario_id: validate_bundle(path)
                for scenario_id, path in generated.items()
            }

            self.assertEqual(
                [],
                bundles["agent-self-report-without-proof"]["evidence"],
            )
            self.assertEqual(
                "relevant_files_changed",
                bundles["tool-log-stale-after-change"]["evidence"][0][
                    "freshness"
                ]["status"],
            )
            self.assertEqual(
                "conflicted",
                bundles["primary-counter-conflict"]["claims"][0]["status"],
            )
            self.assertEqual(
                "unknown",
                bundles["authorization-not-found"]["claims"][0]["status"],
            )
            self.assertTrue(
                bundles["truncated-tool-result"]["evidence"][0]["integrity"][
                    "truncated"
                ]
            )
            self.assertEqual(
                "content",
                bundles["content-identity-fallback"]["sources"][0]["locator"][
                    "identity_kind"
                ],
            )
            self.assertEqual(
                2,
                len(bundles["irrelevant-evidence-present"]["evidence"]),
            )
            old_bundle = bundles["old-bundle-new-commit"]
            self.assertNotEqual(
                old_bundle["manifest"]["task"]["head_ref"],
                old_bundle["evidence"][0]["bindings"]["commit"],
            )
            self.assertEqual(
                "unknown",
                bundles["unknown-claim"]["claims"][0]["status"],
            )
            self.assertEqual(
                [],
                bundles["missing-evidence-overreach"]["claims"][0][
                    "evidence_refs"
                ],
            )

            serialized = json.dumps(
                bundles,
                ensure_ascii=False,
                sort_keys=True,
                default=lambda value: (
                    "<binary>" if isinstance(value, bytes) else str(value)
                ),
            ).lower()
            for sensitive_pattern in (
                r"\bpassword\s*[=:]",
                r"\bauthorization\s*[=:]",
                r"\bbearer\s+[a-z0-9]",
                r"\bgh[pousr]_[a-z0-9_]{12,}",
                r"\bsk-[a-z0-9_-]{12,}",
            ):
                self.assertIsNone(
                    re.search(sensitive_pattern, serialized, re.IGNORECASE)
                )

    def test_generation_is_byte_reproducible_and_refuses_overwrite(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            self.generator.generate_fixtures(first)
            self.generator.generate_fixtures(second)
            self.assertEqual(_snapshot(first), _snapshot(second))

            sentinel = first / "sentinel.txt"
            sentinel.write_text("保留", encoding="utf-8")
            with self.assertRaises(ValueError):
                self.generator.generate_fixtures(first)
            self.assertEqual("保留", sentinel.read_text(encoding="utf-8"))

    def test_scenario_catalog_references_every_generated_bundle(self) -> None:
        catalog: dict[str, Any] = json.loads(
            SCENARIOS.read_text(encoding="utf-8")
        )
        self.assertFalse(catalog["measured_results"])
        scenarios = catalog["scenarios"]
        self.assertEqual(10, len(scenarios))
        self.assertEqual(
            set(self.generator.SCENARIO_IDS),
            {scenario["scenario_id"] for scenario in scenarios},
        )
        for scenario in scenarios:
            with self.subTest(scenario=scenario["scenario_id"]):
                self.assertEqual("not_collected", scenario["availability"])
                self.assertTrue(
                    scenario["fixture_bundle"].endswith(
                        "/" + scenario["scenario_id"]
                    )
                )
                self.assertNotIn("aggregate_score", scenario)


if __name__ == "__main__":
    unittest.main()
