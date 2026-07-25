from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path
from typing import Any

from aet.evidence_core import CandidateError, build_evidence_candidates
from aet.observations import (
    ObservationError,
    extract_observations,
    filter_relevant_observations,
)


FIXTURE = Path(__file__).parent / "fixtures" / "observations" / "records.json"
INVESTIGATION_ID = "investigation-observation-fixture"
QUESTION = "Did the authentication tests pass?"
RECORD_TO_OBSERVATION_TYPE = {
    "meta": "run_metadata",
    "user": None,
    "assistant": "agent_statement",
    "reasoning": "agent_reasoning",
    "tool_call": "agent_tool_call",
    "tool_result": "agent_tool_result",
}
STRENGTH_RANK = {
    "context_only": 0,
    "observed": 1,
    "corroborated": 2,
    "reproduced": 3,
}


def _records() -> list[dict[str, Any]]:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    records = value.get("records")
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise AssertionError("Observation Fixture 必须包含 records 对象数组")
    return records


def _extract(
    records: list[dict[str, Any]] | None = None,
    *,
    question: str = "",
) -> list[dict[str, Any]]:
    return extract_observations(
        records if records is not None else _records(),
        investigation_id=INVESTIGATION_ID,
        question=question,
    )


def _candidates(
    observations: list[dict[str, Any]],
    *,
    question: str = "",
) -> list[dict[str, Any]]:
    return build_evidence_candidates(
        observations,
        investigation_id=INVESTIGATION_ID,
        question=question,
    )


def _observations_for_record(
    observations: list[dict[str, Any]],
    record_id: str,
) -> list[dict[str, Any]]:
    return [
        observation
        for observation in observations
        if record_id in observation["source_refs"]
    ]


class ObservationCandidateTests(unittest.TestCase):
    def test_all_six_run_record_types_map_to_declared_observation_types(self) -> None:
        records = _records()
        observations = _extract(records)
        observed_record_types: set[str] = set()
        sequence = [
            item for item in observations if item["type"] == "run_sequence"
        ]
        self.assertEqual(1, len(sequence))

        for record in records:
            direct = [
                item
                for item in observations
                if item["type"] != "run_sequence"
                and item["source_refs"][0] == record["record_id"]
            ]
            expected_type = RECORD_TO_OBSERVATION_TYPE[record["record_type"]]
            if expected_type is None:
                self.assertFalse(direct)
                self.assertIn(record["record_id"], sequence[0]["source_refs"])
            else:
                self.assertTrue(
                    direct,
                    f"记录未生成直接 Observation：{record['record_id']}",
                )
                self.assertTrue(
                    all(item["type"] == expected_type for item in direct),
                    f"记录类型映射错误：{record['record_type']}",
                )
            observed_record_types.add(record["record_type"])

        self.assertEqual(set(RECORD_TO_OBSERVATION_TYPE), observed_record_types)

    def test_observation_and_candidate_ids_are_stable_and_output_is_deterministic(
        self,
    ) -> None:
        records = _records()
        first_observations = _extract(records)
        second_observations = _extract(copy.deepcopy(records))
        self.assertEqual(first_observations, second_observations)
        self.assertEqual(
            len(first_observations),
            len({item["id"] for item in first_observations}),
        )

        reversed_observations = _extract(list(reversed(copy.deepcopy(records))))
        first_ids = {
            (item["type"], tuple(item["source_refs"])): item["id"]
            for item in first_observations
            if item["type"] != "run_sequence"
        }
        reversed_ids = {
            (item["type"], tuple(item["source_refs"])): item["id"]
            for item in reversed_observations
            if item["type"] != "run_sequence"
        }
        self.assertEqual(first_ids, reversed_ids)

        first_candidates = _candidates(first_observations)
        second_candidates = _candidates(copy.deepcopy(second_observations))
        self.assertEqual(first_candidates, second_candidates)
        self.assertEqual(
            len(first_candidates),
            len({item["id"] for item in first_candidates}),
        )

    def test_question_relevance_filters_unrelated_observations(self) -> None:
        observations = _extract()
        filtered = filter_relevant_observations(observations, QUESTION)
        direct = _extract(question=QUESTION)
        self.assertEqual(filtered, direct)
        source_refs = {
            source_ref
            for observation in filtered
            for source_ref in observation["source_refs"]
        }
        self.assertNotIn("1f3532b4bf67bfe3bb3316cebc72983664a647aaf06b9cc9cfd8abc0c6b44398", source_refs)
        self.assertIn("864a1ce381eb3cf32cbbc37e01249c4009cf163160a7bcffd2d7bf4458a6b73c", source_refs)
        self.assertIn("0d5b4844c6309fe441c53d7359ba84f17da663c2fd820d85abaec8e0bfda9248", source_refs)

        filtered_candidates = _candidates(observations, question=QUESTION)
        self.assertTrue(filtered_candidates)
        self.assertNotIn(
            "1f3532b4bf67bfe3bb3316cebc72983664a647aaf06b9cc9cfd8abc0c6b44398",
            {
                source_ref
                for candidate in filtered_candidates
                for source_ref in candidate["source_refs"]
            },
        )

    def test_every_observation_declares_nonempty_proof_boundaries(self) -> None:
        for observation in _extract():
            with self.subTest(observation=observation["id"]):
                for field in ("proves", "does_not_prove"):
                    self.assertIsInstance(observation[field], list)
                    self.assertTrue(observation[field])
                    self.assertTrue(
                        all(
                            isinstance(statement, str) and statement
                            for statement in observation[field]
                        )
                    )

    def test_self_reports_and_tool_results_cannot_exceed_strength_ceiling(self) -> None:
        observations = _extract()
        candidates = _candidates(observations)
        observations_by_id = {item["id"]: item for item in observations}

        self_report_candidates = [
            candidate
            for candidate in candidates
            if any(
                observations_by_id[reference]["reliability"] == "self_report"
                for reference in candidate["observation_refs"]
            )
        ]
        self.assertTrue(self_report_candidates)
        self.assertTrue(
            all(
                candidate["proposed_strength"] == "context_only"
                for candidate in self_report_candidates
            )
        )

        tool_result_candidates = [
            candidate
            for candidate in candidates
            if any(
                observations_by_id[reference]["type"] == "agent_tool_result"
                for reference in candidate["observation_refs"]
            )
        ]
        self.assertTrue(tool_result_candidates)
        self.assertTrue(
            all(
                STRENGTH_RANK[candidate["proposed_strength"]]
                <= STRENGTH_RANK["observed"]
                for candidate in tool_result_candidates
            )
        )
        self.assertTrue(
            all(candidate["status"] == "unverified" for candidate in candidates)
        )

    def test_reasoning_is_observed_but_never_promoted_to_fact_candidate(self) -> None:
        observations = _extract()
        reasoning = [
            item for item in observations if item["type"] == "agent_reasoning"
        ]
        self.assertTrue(reasoning)
        reasoning_ids = {item["id"] for item in reasoning}
        candidates = _candidates(observations)
        self.assertTrue(
            all(
                reasoning_ids.isdisjoint(candidate["observation_refs"])
                for candidate in candidates
            )
        )
        self.assertTrue(
            all(item["does_not_prove"] for item in reasoning),
        )

    def test_opposing_tool_results_generate_counter_evidence_candidate(self) -> None:
        observations = _extract()
        candidates = _candidates(observations)
        counter_candidates = [
            item
            for item in candidates
            if item["candidate_type"] == "counter_evidence"
        ]
        self.assertTrue(counter_candidates)
        self.assertTrue(
            any(
                "c7891d04140fc3aad06194e0b0332948301301f71f32adf6245403e98bfcf895" in candidate["source_refs"]
                for candidate in counter_candidates
            )
        )
        self.assertTrue(
            any(
                candidate["candidate_type"] == "tool_observation"
                and "0d5b4844c6309fe441c53d7359ba84f17da663c2fd820d85abaec8e0bfda9248" in candidate["source_refs"]
                for candidate in candidates
            )
        )
        self.assertTrue(
            all(
                candidate["proposed_strength"] == "observed"
                for candidate in counter_candidates
            )
        )

    def test_relevance_keeps_a_linked_failure_as_counter_evidence(self) -> None:
        records = [
            {
                "record_id": "call-authentication",
                "record_type": "tool_call",
                "tool_call_id": "call-1",
                "tool_name": "shell",
                "arguments_json": '{"command":"curl /authentication"}',
            },
            {
                "record_id": "result-permission-denied",
                "record_type": "tool_result",
                "tool_call_id": "call-1",
                "linked_tool_call_record_id": "call-authentication",
                "result_json": '{"exit_code":1,"output":"permission denied"}',
            },
        ]
        observations = _extract(records, question="Did authentication succeed?")
        candidates = _candidates(observations)
        self.assertIn(
            "result-permission-denied",
            {
                source_ref
                for observation in observations
                for source_ref in observation["source_refs"]
            },
        )
        self.assertTrue(
            any(
                candidate["candidate_type"] == "counter_evidence"
                and "result-permission-denied" in candidate["source_refs"]
                for candidate in candidates
            )
        )

    def test_unknown_and_malformed_records_fail_closed(self) -> None:
        valid = _records()[1]
        unknown = copy.deepcopy(valid)
        unknown["record_type"] = "future_record"
        malformed = copy.deepcopy(valid)
        malformed.pop("record_id")

        for name, records in (
            ("unknown", [unknown]),
            ("malformed", [malformed]),
        ):
            with self.subTest(record=name):
                with self.assertRaises(ObservationError):
                    _extract(records)

        malformed_observation = _extract([valid])[0]
        malformed_observation.pop("does_not_prove")
        with self.assertRaises(CandidateError):
            _candidates([malformed_observation])


if __name__ == "__main__":
    unittest.main()
