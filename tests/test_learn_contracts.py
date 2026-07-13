from __future__ import annotations

import hashlib
import copy
import json
import math
import re
import tempfile
import unittest
from pathlib import Path

from aet.evolution import CandidateError, constitution_sha256, default_registry, load_candidate
from aet.learn import LearnError, verify_suite
from aet.learn_contracts import HARD_REQUIREMENTS_BY_TASK_VERSION, validate_learn_task_v2


SHA_A = hashlib.sha256(b"baseline").hexdigest()
SHA_B = hashlib.sha256(b"candidate").hexdigest()


def schema_failures(value: object, schema: dict, root: Path, path: str = "$") -> list[str]:
    """Small stdlib validator for the schema keywords used by candidate v2."""
    if "$ref" in schema:
        target = json.loads((root / schema["$ref"]).read_text(encoding="utf-8"))
        return schema_failures(value, target, root, path)
    failures: list[str] = []
    if "const" in schema and value != schema["const"]:
        failures.append(f"{path} must equal const")
    if "enum" in schema and value not in schema["enum"]:
        failures.append(f"{path} is outside enum")
    expected_type = schema.get("type")
    type_matches = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str), "integer": isinstance(value, int) and not isinstance(value, bool),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool), "null": value is None,
        "boolean": isinstance(value, bool),
    }
    if isinstance(expected_type, str) and not type_matches.get(expected_type, True):
        return failures + [f"{path} must be {expected_type}"]
    if isinstance(value, dict):
        required = schema.get("required", [])
        failures.extend(f"{path}.{key} is required" for key in required if key not in value)
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            failures.extend(f"{path}.{key} is additional" for key in value if key not in properties)
        for key, child in value.items():
            if key in properties:
                failures.extend(schema_failures(child, properties[key], root, f"{path}.{key}"))
    if isinstance(value, list):
        if isinstance(schema.get("minItems"), int) and len(value) < schema["minItems"]:
            failures.append(f"{path} has too few items")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value):
            failures.append(f"{path} must contain unique items")
        if isinstance(schema.get("items"), dict):
            for index, child in enumerate(value):
                failures.extend(schema_failures(child, schema["items"], root, f"{path}[{index}]"))
    if isinstance(value, str):
        if isinstance(schema.get("minLength"), int) and len(value) < schema["minLength"]:
            failures.append(f"{path} is too short")
        if isinstance(schema.get("pattern"), str) and re.search(schema["pattern"], value) is None:
            failures.append(f"{path} does not match pattern")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and isinstance(schema.get("minimum"), (int, float)) and value < schema["minimum"]:
        failures.append(f"{path} is below minimum")
    return failures


def valid_task() -> dict:
    return {
        "schema_version": "2.0",
        "task_id": "TASK-1",
        "prompt": "Run the check.",
        "fixture": {"source": "fixture"},
        "runner": {"allowed": ["scripted"], "required_capabilities": ["supports_non_interactive"]},
        "policy": {
            "network": "deny",
            "timeout_seconds": 10,
            "max_commands": 2,
            "max_changed_files": 1,
            "allowed_commands": ["aet trace"],
            "allowed_write_paths": [".aet/**"],
            "forbidden_write_paths": ["src/**"],
            "environment_allowlist": ["PATH"],
        },
        "expected_behavior": {
            "required_surfaces": ["trace"],
            "required_proof_ids": ["tests"],
            "required_artifacts": ["trace"],
            "required_final_claims": ["evidence_path"],
            "forbidden_claims_without_proof": ["tests_passed"],
            "unknown_must_be_preserved": True,
            "required_tool_calls": [
                {"tool": "lookup", "arguments": {"id": "42"}, "arguments_match": "exact"}
            ],
        },
        "scoring": {
            "hard_requirements": ["fresh_trace_required", "required_tool_calls"],
            "soft_metrics": ["minimal_workflow"],
        },
    }


class LearnTaskContractTests(unittest.TestCase):
    def test_hard_requirement_mapping_is_bound_to_task_contract_version(self) -> None:
        self.assertEqual({"2.0"}, set(HARD_REQUIREMENTS_BY_TASK_VERSION))
        self.assertIn("required_tool_calls", HARD_REQUIREMENTS_BY_TASK_VERSION["2.0"])

    def test_valid_task_v2_is_accepted(self) -> None:
        self.assertEqual([], validate_learn_task_v2(valid_task()))

    def test_unknown_hard_requirement_fails_closed(self) -> None:
        task = valid_task()
        task["scoring"]["hard_requirements"] = ["model_says_ok"]
        self.assertIn("unknown hard requirement: model_says_ok", validate_learn_task_v2(task))

    def test_unknown_keys_and_wrong_types_fail_closed(self) -> None:
        mutations = (
            ("policy key", lambda task: task["policy"].update({"shell": True}), "policy contains unknown key: shell"),
            ("policy type", lambda task: task["policy"].update({"max_commands": "2"}), "policy.max_commands must be a non-negative integer"),
            ("network", lambda task: task["policy"].update({"network": "best-effort"}), "policy.network must be allow, deny, or enforced-deny"),
            ("expected key", lambda task: task["expected_behavior"].update({"judge_prompt": "pass"}), "expected_behavior contains unknown key: judge_prompt"),
            ("runner", lambda task: task["runner"].update({"command": "agent"}), "runner contains unknown key: command"),
            ("scoring", lambda task: task["scoring"].update({"weights": {"trust": 1}}), "scoring contains unknown key: weights"),
        )
        for label, mutate, expected in mutations:
            with self.subTest(label=label):
                task = valid_task()
                mutate(task)
                self.assertIn(expected, validate_learn_task_v2(task))

    def test_optional_top_level_fields_still_have_closed_types(self) -> None:
        task = valid_task()
        task.update({"title": 7, "category": [], "script": "shell"})
        failures = validate_learn_task_v2(task)
        self.assertIn("title must be a string", failures)
        self.assertIn("category must be a string", failures)
        self.assertIn("script must be an array or object", failures)

    def test_required_tool_call_contract_rejects_ambiguous_arguments(self) -> None:
        task = valid_task()
        task["expected_behavior"]["required_tool_calls"] = [{"tool": "lookup", "arguments": [], "arguments_match": "fuzzy"}]
        failures = validate_learn_task_v2(task)
        self.assertIn("expected_behavior.required_tool_calls[0].arguments must be a JSON object", failures)
        self.assertIn("expected_behavior.required_tool_calls[0].arguments_match must be exact or subset", failures)

        task = valid_task()
        task["expected_behavior"]["required_tool_calls"] = [{"tool": "lookup"}]
        failures = validate_learn_task_v2(task)
        self.assertIn("expected_behavior.required_tool_calls[0].arguments is required", failures)
        self.assertIn("expected_behavior.required_tool_calls[0].arguments_match is required", failures)

    def test_timeout_rejects_non_finite_numbers_and_json_constants(self) -> None:
        for timeout in (math.nan, math.inf, -math.inf):
            with self.subTest(timeout=timeout):
                task = valid_task()
                task["policy"]["timeout_seconds"] = timeout
                self.assertIn("policy.timeout_seconds must be a positive finite number", validate_learn_task_v2(task))
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "task.json").write_text(json.dumps(valid_task()).replace("10", "NaN", 1), encoding="utf-8")
            with self.assertRaises(LearnError):
                verify_suite(suite=root, output=root / "verification.json")

    def test_suite_discovery_reports_malformed_schema_v2_alongside_valid_task(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "fixture").mkdir()
            (root / "valid.json").write_text(json.dumps(valid_task()), encoding="utf-8")
            malformed = valid_task()
            malformed.pop("task_id")
            malformed["prompt"] = 7
            (root / "malformed.json").write_text(json.dumps(malformed), encoding="utf-8")
            result = verify_suite(suite=root, output=root / "verification.json")
            self.assertEqual("FAIL", result["status"])
            self.assertEqual(2, result["task_count"])
            self.assertTrue(any(identifier.startswith("INVALID-TASK-") for identifier in result["task_ids"]))
            self.assertTrue(any("task_id must be a non-empty string" in failure for failure in result["failures"]))

    def test_suite_verification_reports_unknown_hard_requirement_as_fail(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "fixture").mkdir()
            task = valid_task()
            task["scoring"]["hard_requirements"] = ["model_says_ok"]
            (root / "task.json").write_text(json.dumps(task), encoding="utf-8")
            result = verify_suite(suite=root, output=root / "verification.json")
            self.assertEqual("FAIL", result["status"])
            self.assertTrue(any("unknown hard requirement" in failure for failure in result["failures"]))


class CandidateSchemaTests(unittest.TestCase):
    def test_legacy_schema_is_only_a_deprecated_reference(self) -> None:
        schema = json.loads(Path("schemas/learn-candidate.schema.json").read_text(encoding="utf-8"))
        self.assertEqual("evolution-candidate-v2.schema.json", schema["$ref"])
        self.assertIs(schema["deprecated"], True)
        self.assertNotIn("properties", schema)

    def test_canonical_schema_and_runtime_accept_every_registered_target(self) -> None:
        schema_root = Path("schemas")
        schema = json.loads((schema_root / "evolution-candidate-v2.schema.json").read_text(encoding="utf-8"))
        alias = json.loads((schema_root / "learn-candidate.schema.json").read_text(encoding="utf-8"))
        schema_targets = set(schema["properties"]["target"]["properties"]["type"]["enum"])
        registry_targets = {adapter.target_type for adapter in default_registry().list()}
        self.assertEqual(registry_targets, schema_targets)
        paths = {
            "skill": "/editable_blocks/route",
            "audit-rule": "/rules/-",
            "audit-profile": "/rules/AET-1",
            "review-policy": "/proof_requirements/-",
            "trace-validator": "/requirements/-",
            "triage-policy": "/weights/risk",
        }
        for target_type, operation_path in paths.items():
            with self.subTest(target_type=target_type):
                document = {
                    "schema_version": "evolution-candidate/v2",
                    "report_kind": "evolution_candidate",
                    "candidate_id": f"CAND-{target_type.upper()}",
                    "target": {"type": target_type, "path": f"targets/{target_type}", "baseline_sha256": SHA_A},
                    "candidate_sha256": SHA_B,
                    "operations": [{"op": "add", "path": operation_path, "value": 1}],
                    "budgets": {"max_operations": 1},
                    "adoption": "human_required",
                    "constitution_sha256": constitution_sha256(),
                }
                self.assertEqual([], schema_failures(document, schema, schema_root))
                self.assertEqual([], schema_failures(document, alias, schema_root))
                self.assertEqual(target_type, load_candidate(document, candidate_content=b"candidate").target.target_type)
                required = set(schema["required"])
                self.assertTrue(required <= set(document))
                self.assertFalse(set(document) - set(schema["properties"]))
                for mutation in ({key: value for key, value in document.items() if key != "adoption"}, {**document, "unexpected": True}):
                    with self.assertRaises(CandidateError):
                        load_candidate(mutation, candidate_content=b"candidate")

                nested_mutations = []
                for section, mutation in (
                    ("target missing", lambda item: item["target"].pop("path")),
                    ("target additional", lambda item: item["target"].update({"extra": True})),
                    ("target type", lambda item: item["target"].update({"path": 7})),
                    ("target enum", lambda item: item["target"].update({"type": "prompt"})),
                    ("operation missing", lambda item: item["operations"][0].pop("op")),
                    ("operation additional", lambda item: item["operations"][0].update({"shell": True})),
                    ("operation type", lambda item: item["operations"][0].update({"path": 7})),
                    ("operation enum", lambda item: item["operations"][0].update({"op": "remove"})),
                    ("budget missing", lambda item: item["budgets"].pop("max_operations")),
                    ("budget additional", lambda item: item["budgets"].update({"tokens": 1})),
                    ("budget type", lambda item: item["budgets"].update({"max_operations": "1"})),
                    ("budget minimum", lambda item: item["budgets"].update({"max_operations": 0})),
                ):
                    malformed = copy.deepcopy(document)
                    mutation(malformed)
                    nested_mutations.append((section, malformed))
                for section, malformed in nested_mutations:
                    with self.subTest(target_type=target_type, section=section):
                        self.assertTrue(schema_failures(malformed, schema, schema_root))
                        self.assertTrue(schema_failures(malformed, alias, schema_root))


if __name__ == "__main__":
    unittest.main()
