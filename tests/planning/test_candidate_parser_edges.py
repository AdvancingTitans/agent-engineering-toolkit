from __future__ import annotations

import json
import unittest
from copy import deepcopy

from aet.planning.candidate_parser import (
    MAX_CANDIDATE_BYTES,
    MAX_CANDIDATE_ITEMS,
    parse_candidate,
    strict_json_loads,
)
from aet.planning.errors import PlanningError

from tests.planning.test_models import candidate_value


class CandidateParserEdgeTests(unittest.TestCase):
    def test_strict_json_input_budgets_encoding_types_and_constants(self) -> None:
        values = [
            b"x" * (MAX_CANDIDATE_BYTES + 1),
            "x" * (MAX_CANDIDATE_BYTES + 1),
            b"\xff",
            42,
            '{"value":NaN}',
            "{",
        ]
        for value in values:
            with self.subTest(kind=type(value).__name__, size=len(value) if hasattr(value, "__len__") else None):
                with self.assertRaises(PlanningError):
                    strict_json_loads(value)
        self.assertEqual({"value": 1}, strict_json_loads(b'{"value":1}'))

    def test_candidate_top_level_and_nested_shape_failures(self) -> None:
        invalid_values = []
        invalid_values.append([])
        value = candidate_value()
        value["schema_version"] = "plan-candidate/9"
        invalid_values.append(value)
        value = candidate_value()
        value["request_id"] = ""
        invalid_values.append(value)
        value = candidate_value()
        value["coverage_claim"] = "COMPLETE"
        invalid_values.append(value)
        value = candidate_value()
        value["assumptions"] = {}
        invalid_values.append(value)
        value = candidate_value()
        value["assumptions"] = [{}] * (MAX_CANDIDATE_ITEMS + 1)
        invalid_values.append(value)
        value = candidate_value()
        value["unresolved"] = ["not-an-object"]
        invalid_values.append(value)
        value = candidate_value()
        value["edit_items"] = ["not-an-object"]
        invalid_values.append(value)
        value = candidate_value()
        value["verification_steps"] = ["not-an-object"]
        invalid_values.append(value)
        for number, value in enumerate(invalid_values):
            with self.subTest(number=number):
                with self.assertRaises(PlanningError):
                    parse_candidate(json.dumps(value))

    def test_edit_and_verification_field_failures(self) -> None:
        mutations = []

        def mutate_edit(field, value):
            candidate = deepcopy(candidate_value())
            candidate["edit_items"][0][field] = value
            mutations.append(candidate)

        mutate_edit("edit_id", "")
        mutate_edit("disposition", "WRITE")
        mutate_edit("symbol", 1)
        mutate_edit("source_range", "1-2")
        mutate_edit("source_range", {"start_line": 4, "end_line": 2})
        mutate_edit("source_range", {"start_line": 1})
        mutate_edit("tests", ["same", "same"])
        candidate = deepcopy(candidate_value())
        candidate["edit_items"][0].pop("risks")
        mutations.append(candidate)
        candidate = deepcopy(candidate_value())
        candidate["verification_steps"][0]["status"] = "PASS"
        mutations.append(candidate)
        candidate = deepcopy(candidate_value())
        candidate["verification_steps"][0]["command"] = []
        mutations.append(candidate)
        candidate = deepcopy(candidate_value())
        candidate["verification_steps"][0]["edit_refs"] = [""]
        mutations.append(candidate)
        candidate = deepcopy(candidate_value())
        candidate["verification_steps"][0].pop("expected_result")
        mutations.append(candidate)
        for number, value in enumerate(mutations):
            with self.subTest(number=number):
                with self.assertRaises(PlanningError):
                    parse_candidate(json.dumps(value))


if __name__ == "__main__":
    unittest.main()
