from __future__ import annotations

import json
import tempfile
import time
import unittest
from copy import deepcopy
from pathlib import Path

from aet.planning.candidate_parser import parse_candidate
from aet.planning.context_builder import build_planning_context
from aet.planning.package_builder import build_plan_package
from aet.planning.request_normalizer import RequestOverrides, normalize_request
from aet.planning.validator import validate_plan_candidate

from tests.planning.test_models import candidate_value
from tests.planning.test_validator import context_value


class PlanningPerformanceTests(unittest.TestCase):
    def test_context_validator_renderer_and_package_stay_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            workspace = Path(raw)
            source = workspace / "src/example.py"
            source.parent.mkdir(parents=True)
            source.write_text("def run():\n    return 1\n", encoding="utf-8")
            request = normalize_request(
                "Plan one bounded source change.",
                workspace=workspace,
                explicit=RequestOverrides(allowed_paths=["src/example.py"]),
            )
            started = time.perf_counter()
            context = build_planning_context(
                request,
                workspace=workspace,
            )
            context_seconds = time.perf_counter() - started
            self.assertLess(context_seconds, 5.0)

            value = candidate_value()
            value["edit_items"] = []
            for number in range(100):
                item = deepcopy(candidate_value()["edit_items"][0])
                item["edit_id"] = f"EDIT-{number:03d}"
                item["dependencies"] = []
                value["edit_items"].append(item)
            value["verification_steps"][0]["edit_refs"] = [
                item["edit_id"] for item in value["edit_items"]
            ]
            candidate = parse_candidate(json.dumps(value))
            validation_context = context_value()
            started = time.perf_counter()
            result = validate_plan_candidate(validation_context, candidate)
            validation_seconds = time.perf_counter() - started
            self.assertLess(validation_seconds, 2.0)

            started = time.perf_counter()
            package = build_plan_package(
                validation_context,
                result,
                workspace / "plan",
            )
            package_seconds = time.perf_counter() - started
            self.assertLess(package_seconds, 2.0)
            package_bytes = sum(
                item.stat().st_size
                for item in package.rglob("*")
                if item.is_file()
            )
            self.assertLessEqual(package_bytes, 10_000_000)


if __name__ == "__main__":
    unittest.main()
