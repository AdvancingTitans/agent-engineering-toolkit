from __future__ import annotations

import copy
import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from aet.investigation import (
    PortableInvestigationError,
    investigate_run,
    write_investigation_result,
)
from aet.quick.proof import quick_proof


ROOT = Path(__file__).parent.parent
RECORDS_FIXTURE = (
    Path(__file__).parent / "fixtures" / "observations" / "records.json"
)
SCHEMA_ROOT = ROOT / "schemas" / "investigation" / "v1"


def _records() -> list[dict[str, Any]]:
    value = json.loads(RECORDS_FIXTURE.read_text(encoding="utf-8"))
    records = value.get("records")
    if not isinstance(records, list) or not all(
        isinstance(record, dict) for record in records
    ):
        raise AssertionError("Portable Investigator Fixture 必须包含 records 对象数组")
    return records


def _request(
    *,
    investigation_id: str = "investigation-portable-001",
) -> dict[str, Any]:
    return {
        "protocol_version": "1.0",
        "investigation_id": investigation_id,
        "question": "Did the authentication tests pass?",
        "task": {
            "task_id": "task-portable-001",
            "request": "Verify the recorded authentication test result.",
        },
        "hypotheses": {
            "primary": "Authentication tests passed.",
            "competing": [
                "Authentication tests failed or the recorded result is stale."
            ],
        },
        "requested_evidence": ["test_execution", "test_freshness"],
        "run_sources": [
            {
                "id": "run-source-001",
                "source_type": "codex",
                "run_group_id": "run-observation-fixture",
            }
        ],
        "policy": {
            "schema_version": "portable-investigation-policy/1.0",
            "allowed_tools": ["run.read"],
            "denied_tools": [
                "file.write",
                "git.commit",
                "git.push",
                "git.merge",
            ],
            "budgets": {
                "max_tool_calls": 0,
                "max_evidence_candidates": 20,
                "max_verified_evidence": 0,
                "max_run_records_read": 100,
                "max_blob_bytes_read": 0,
            },
            "command_policy": {
                "allow_execution": False,
                "allowed_command_prefixes": [],
            },
            "workspace_policy": {
                "read_only": True,
            },
            "privacy_policy": {
                "redact_secrets": True,
                "export_reasoning": False,
                "export_raw_tool_output": False,
            },
            "require_competing_hypothesis": True,
            "require_disconfirming_search": True,
        },
    }


def _verification_request() -> dict[str, Any]:
    request = _request()
    request["policy"]["allowed_tools"] = [
        "run.read",
        "proof.inspect",
        "freshness.check",
    ]
    request["policy"]["budgets"]["max_tool_calls"] = 2
    request["policy"]["budgets"]["max_verified_evidence"] = 2
    return request


def _write_matching_proof(
    root: Path,
    argv: list[str] | None = None,
) -> Path:
    command = argv or ["pytest", "tests/auth"]
    executable = root / "bin" / "pytest"
    executable.parent.mkdir(parents=True)
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o755)
    relevant = root / "tests" / "auth" / "test_ok.py"
    relevant.parent.mkdir(parents=True)
    relevant.write_text("assert True\n", encoding="utf-8")
    (root / "tests" / "__init__.py").write_text("", encoding="utf-8")
    (root / "tests" / "test_example.py").write_text(
        "import unittest\n\n"
        "class ExampleTests(unittest.TestCase):\n"
        "    def test_ok(self):\n"
        "        self.assertTrue(True)\n",
        encoding="utf-8",
    )
    proof = root / "proof.json"
    with _working_directory(root), patch.dict(
        os.environ,
        {"PATH": f"{root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"},
    ):
        receipt, exit_code = quick_proof(
            command,
            proof,
            relevant_paths=["tests/auth/test_ok.py"],
        )
    if exit_code != 0 or receipt["authoritative_status"] != "PASS":
        raise AssertionError("确定性 Proof Fixture 必须成功")
    return proof


@contextmanager
def _working_directory(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class PortableInvestigationTests(unittest.TestCase):
    def test_valid_read_only_request_produces_bounded_unknown_result(self) -> None:
        result = investigate_run(_request(), _records())
        self.assertEqual("portable-investigation-result/1.0", result["schema_version"])
        self.assertEqual("investigation-portable-001", result["investigation_id"])
        self.assertEqual("unknown", result["status"])
        self.assertTrue(result["observations"])
        self.assertTrue(result["evidence_candidates"])
        self.assertEqual([], result["verified_evidence"])
        self.assertTrue(result["ledger"])
        self.assertTrue(result["unresolved"])
        self.assertEqual("tool_unavailable", result["stop"]["reason"])
        self.assertTrue(result["stop"]["bounded_result"])

        observation_ids = {item["id"] for item in result["observations"]}
        candidate_ids = {item["id"] for item in result["evidence_candidates"]}
        for entry in result["ledger"]:
            self.assertTrue(set(entry["observation_refs"]) <= observation_ids)
            self.assertTrue(
                set(entry["evidence_candidate_refs"]) <= candidate_ids
            )

    def test_authorized_proof_and_freshness_verify_matching_command_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof = _write_matching_proof(root)
            request = _verification_request()
            with _working_directory(root), patch.dict(
                os.environ,
                {"PATH": f"{root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"},
            ):
                result = investigate_run(
                    request,
                    _records(),
                    workspace=root,
                    proof_paths=[proof],
                )

            self.assertEqual("supported", result["status"])
            self.assertEqual("question_answered", result["stop"]["reason"])
            self.assertEqual(1, len(result["verified_evidence"]))
            self.assertEqual("reproduced", result["verified_evidence"][0]["strength"])
            self.assertEqual("current", result["verified_evidence"][0]["freshness"]["status"])
            self.assertEqual(2, result["usage"]["tool_calls"])
            self.assertEqual(1, result["usage"]["verified_evidence"])
            self.assertTrue(result["verification_sources"])
            self.assertTrue(
                any(
                    item["status"] == "verified"
                    and item["candidate_type"] == "command_observation"
                    for item in result["evidence_candidates"]
                )
            )
            write_investigation_result(result, root / "investigation.json")

    def test_stale_proof_remains_historical_and_does_not_answer_current_question(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof = _write_matching_proof(root)
            (root / "tests" / "auth" / "test_ok.py").write_text(
                "assert False\n",
                encoding="utf-8",
            )
            request = _verification_request()
            with _working_directory(root), patch.dict(
                os.environ,
                {"PATH": f"{root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"},
            ):
                result = investigate_run(
                    request,
                    _records(),
                    workspace=root,
                    proof_paths=[proof],
                )
            self.assertEqual("unknown", result["status"])
            self.assertEqual(
                "relevant_files_changed",
                result["verified_evidence"][0]["freshness"]["status"],
            )
            self.assertFalse(result["verified_evidence"][0]["supports"])

    def test_proof_requires_explicit_tool_authority_workspace_and_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            proof = _write_matching_proof(root)

            unauthorized = _request()
            with self.assertRaises(PortableInvestigationError):
                investigate_run(
                    unauthorized,
                    _records(),
                    workspace=root,
                    proof_paths=[proof],
                )

            with self.assertRaises(PortableInvestigationError):
                investigate_run(
                    _verification_request(),
                    _records(),
                    proof_paths=[proof],
                )

            limited = _verification_request()
            limited["policy"]["budgets"]["max_tool_calls"] = 1
            with _working_directory(root), patch.dict(
                os.environ,
                {"PATH": f"{root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"},
            ):
                result = investigate_run(
                    limited,
                    _records(),
                    workspace=root,
                    proof_paths=[proof],
                )
            self.assertEqual("budget_exhausted", result["stop"]["reason"])
            self.assertEqual([], result["verified_evidence"])
            self.assertEqual(1, result["usage"]["tool_calls"])
            write_investigation_result(result, root / "limited-investigation.json")

    def test_proof_path_escape_and_symlink_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_value, tempfile.TemporaryDirectory() as outside_value:
            root = Path(workspace_value)
            outside = Path(outside_value)
            proof = _write_matching_proof(outside)
            request = _verification_request()
            with self.assertRaises(PortableInvestigationError):
                investigate_run(
                    request,
                    _records(),
                    workspace=root,
                    proof_paths=[proof],
                )
            link = root / "proof-link.json"
            link.symlink_to(proof)
            with self.assertRaises(PortableInvestigationError):
                investigate_run(
                    request,
                    _records(),
                    workspace=root,
                    proof_paths=[link],
                )

    def test_missing_competing_hypothesis_is_rejected(self) -> None:
        request = _request()
        request["hypotheses"]["competing"] = []
        with self.assertRaises(PortableInvestigationError):
            investigate_run(request, _records())

    def test_writable_workspace_policy_is_rejected(self) -> None:
        request = _request()
        request["policy"]["workspace_policy"]["read_only"] = False
        with self.assertRaises(PortableInvestigationError):
            investigate_run(request, _records())

    def test_structured_policy_extensions_are_preserved(self) -> None:
        request = _request()
        request["policy"]["extensions"] = {"host": {"mode": "read-only"}}
        result = investigate_run(request, _records())
        self.assertEqual(
            {"host": {"mode": "read-only"}},
            result["policy"]["extensions"],
        )

    def test_conflicting_and_write_capable_tools_are_rejected(self) -> None:
        overlap = _request()
        overlap["policy"]["denied_tools"].append("run.read")
        with self.assertRaises(PortableInvestigationError):
            investigate_run(overlap, _records())

        for unsafe in ("file.write", "git.commit", "git.push", "git.merge"):
            with self.subTest(unsafe_tool=unsafe):
                request = _request()
                request["policy"]["allowed_tools"].append(unsafe)
                request["policy"]["denied_tools"].remove(unsafe)
                with self.assertRaises(PortableInvestigationError):
                    investigate_run(request, _records())

    def test_run_and_candidate_budgets_stop_before_overrun(self) -> None:
        run_limited = _request()
        run_limited["policy"]["budgets"]["max_run_records_read"] = 1
        run_result = investigate_run(run_limited, _records())
        self.assertEqual(1, run_result["usage"]["run_records_read"])
        self.assertEqual("budget_exhausted", run_result["stop"]["reason"])
        self.assertTrue(run_result["unresolved"])

        candidate_limited = _request()
        candidate_limited["policy"]["budgets"]["max_evidence_candidates"] = 0
        candidate_result = investigate_run(candidate_limited, _records())
        self.assertEqual([], candidate_result["evidence_candidates"])
        self.assertEqual(0, candidate_result["usage"]["evidence_candidates"])
        self.assertEqual(
            "budget_exhausted",
            candidate_result["stop"]["reason"],
        )

    def test_all_four_runtime_budget_fields_are_nonnegative_and_accounted(self) -> None:
        budget_fields = (
            "max_run_records_read",
            "max_evidence_candidates",
            "max_verified_evidence",
            "max_tool_calls",
        )
        for field in budget_fields:
            with self.subTest(budget=field):
                request = _request()
                request["policy"]["budgets"][field] = -1
                with self.assertRaises(PortableInvestigationError):
                    investigate_run(request, _records())

        result = investigate_run(_request(), _records())
        self.assertLessEqual(
            result["usage"]["run_records_read"],
            _request()["policy"]["budgets"]["max_run_records_read"],
        )
        self.assertLessEqual(
            result["usage"]["evidence_candidates"],
            _request()["policy"]["budgets"]["max_evidence_candidates"],
        )
        self.assertEqual(0, result["usage"]["verified_evidence"])
        self.assertEqual(0, result["usage"]["tool_calls"])

    def test_reasoning_is_never_promoted_to_candidate(self) -> None:
        request = _request()
        request["policy"]["privacy_policy"]["export_reasoning"] = True
        result = investigate_run(request, _records())
        reasoning_ids = {
            item["id"]
            for item in result["observations"]
            if item["type"] == "agent_reasoning"
        }
        self.assertTrue(reasoning_ids)
        self.assertTrue(
            all(
                reasoning_ids.isdisjoint(item["observation_refs"])
                for item in result["evidence_candidates"]
            )
        )

    def test_recorded_failure_is_preserved_as_counter_evidence(self) -> None:
        result = investigate_run(_request(), _records())
        counters = [
            item
            for item in result["evidence_candidates"]
            if item["candidate_type"] == "counter_evidence"
        ]
        self.assertTrue(counters)
        self.assertTrue(
            any(
                "c7891d04140fc3aad06194e0b0332948301301f71f32adf6245403e98bfcf895" in item["source_refs"]
                for item in counters
            )
        )
        counter_ids = {item["id"] for item in counters}
        self.assertTrue(
            counter_ids
            <= set(
                result["disconfirming_search"][
                    "counter_evidence_candidate_refs"
                ]
            )
        )
        self.assertTrue(
            counter_ids
            <= set(
                result["findings"][0][
                    "counter_evidence_candidate_refs"
                ]
            )
        )

    def test_stop_conditions_preserve_budget_tool_and_unknown_semantics(self) -> None:
        tool_result = investigate_run(_request(), _records())
        self.assertEqual("tool_unavailable", tool_result["stop"]["reason"])
        self.assertEqual("unknown", tool_result["status"])

        budget_request = _request()
        budget_request["policy"]["budgets"]["max_run_records_read"] = 0
        budget_result = investigate_run(budget_request, _records())
        self.assertEqual("budget_exhausted", budget_result["stop"]["reason"])
        self.assertEqual("unknown", budget_result["status"])

        result_schema = json.loads(
            (SCHEMA_ROOT / "result.schema.json").read_text(encoding="utf-8")
        )
        self.assertIn(
            "unknown",
            result_schema["properties"]["stop"]["properties"]["reason"][
                "enum"
            ],
        )

    def test_repeated_input_is_deterministic(self) -> None:
        request = _request()
        records = _records()
        first = investigate_run(request, records)
        second = investigate_run(
            copy.deepcopy(request),
            copy.deepcopy(records),
        )
        self.assertEqual(first, second)

    def test_writer_rejects_existing_output_and_new_run_uses_new_id(self) -> None:
        first = investigate_run(_request(), _records())
        second = investigate_run(
            _request(investigation_id="investigation-portable-002"),
            _records(),
        )
        self.assertNotEqual(first["investigation_id"], second["investigation_id"])
        self.assertNotEqual(
            first["findings"][0]["id"],
            second["findings"][0]["id"],
        )

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_output = root / "first-result.json"
            second_output = root / "second-result.json"
            write_investigation_result(first, first_output)
            before = first_output.read_bytes()
            with self.assertRaises(PortableInvestigationError):
                write_investigation_result(first, first_output)
            self.assertEqual(before, first_output.read_bytes())
            write_investigation_result(second, second_output)
            self.assertEqual(
                "investigation-portable-002",
                json.loads(second_output.read_text(encoding="utf-8"))[
                    "investigation_id"
                ],
            )

    def test_writer_rejects_malformed_or_promoted_result(self) -> None:
        result = investigate_run(_request(), _records())
        malformed = copy.deepcopy(result)
        malformed["evidence_candidates"][0]["status"] = "verified"
        promoted = copy.deepcopy(result)
        promoted["verified_evidence"] = [{"id": "evidence-not-authorized"}]
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, candidate in (
                ("malformed.json", malformed),
                ("promoted.json", promoted),
            ):
                with self.subTest(name=name):
                    output = root / name
                    with self.assertRaises(PortableInvestigationError):
                        write_investigation_result(candidate, output)
                    self.assertFalse(output.exists())

    def test_three_schemas_parse_and_match_runtime_minimum(self) -> None:
        schemas = {
            name: json.loads(
                (SCHEMA_ROOT / f"{name}.schema.json").read_text(
                    encoding="utf-8"
                )
            )
            for name in ("request", "ledger", "result")
        }
        self.assertTrue(all(schema["$schema"].endswith("2020-12/schema") for schema in schemas.values()))

        request = _request()
        result = investigate_run(request, _records())
        self.assertEqual(
            set(schemas["request"]["required"]),
            set(request),
        )
        self.assertEqual(
            set(schemas["result"]["required"]),
            set(result),
        )
        self.assertEqual("array", schemas["ledger"]["type"])
        ledger_required = set(schemas["ledger"]["items"]["required"])
        ledger_properties = set(
            schemas["ledger"]["items"]["properties"]
        )
        self.assertTrue(result["ledger"])
        self.assertTrue(
            all(
                ledger_required <= set(entry) <= ledger_properties
                for entry in result["ledger"]
            )
        )
        self.assertEqual(
            schemas["request"]["properties"]["protocol_version"]["const"],
            request["protocol_version"],
        )
        self.assertEqual(
            schemas["result"]["properties"]["schema_version"]["const"],
            result["schema_version"],
        )

    def test_secret_bearing_request_fields_are_redacted_or_rejected(self) -> None:
        secret = "token=fixture-secret-value"
        mutations = {
            "question": lambda value: value.update({"question": secret}),
            "task": lambda value: value["task"].update({"request": secret}),
            "primary_hypothesis": lambda value: value["hypotheses"].update(
                {"primary": secret}
            ),
            "competing_hypothesis": lambda value: value["hypotheses"].update(
                {"competing": [secret]}
            ),
            "run_source": lambda value: value["run_sources"][0].update(
                {"id": secret}
            ),
            "requested_evidence": lambda value: value.update(
                {"requested_evidence": [secret]}
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(request_field=name):
                request = _request()
                mutate(request)
                before = copy.deepcopy(request)
                try:
                    result = investigate_run(request, _records())
                except PortableInvestigationError:
                    pass
                else:
                    self.assertNotIn(
                        secret,
                        json.dumps(result, ensure_ascii=False),
                    )
                self.assertEqual(before, request)

    def test_writer_rejects_strengthened_and_malformed_results(self) -> None:
        baseline = investigate_run(_request(), _records())
        mutations = {
            "supported_status": lambda value: value.update(
                {"status": "supported"}
            ),
            "reproduced_candidate": lambda value: value[
                "evidence_candidates"
            ][0].update({"proposed_strength": "reproduced"}),
            "malformed_observations": lambda value: value.update(
                {"observations": "not-an-array"}
            ),
            "malformed_usage": lambda value: value["usage"].update(
                {"tool_calls": "zero"}
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, mutate in mutations.items():
                with self.subTest(result_mutation=name):
                    result = copy.deepcopy(baseline)
                    mutate(result)
                    output = root / f"{name}.json"
                    with self.assertRaises(PortableInvestigationError):
                        write_investigation_result(result, output)
                    self.assertFalse(output.exists())

    def test_dangerous_command_prefixes_are_rejected(self) -> None:
        for prefix in (
            ["sh", "-c"],
            ["bash", "-c"],
            ["rm"],
            ["mv"],
            ["cp"],
        ):
            with self.subTest(command_prefix=prefix):
                request = _request()
                request["policy"]["command_policy"] = {
                    "allow_execution": True,
                    "allowed_command_prefixes": [prefix],
                }
                with self.assertRaises(PortableInvestigationError):
                    investigate_run(request, _records())

    def test_zero_record_budget_does_not_claim_disconfirming_search(self) -> None:
        request = _request()
        request["policy"]["budgets"]["max_run_records_read"] = 0
        result = investigate_run(request, _records())
        self.assertEqual(0, result["usage"]["run_records_read"])
        self.assertEqual([], result["disconfirming_search"]["searched_record_refs"])
        self.assertFalse(result["disconfirming_search"]["performed"])

    def test_optional_task_repository_must_be_a_string(self) -> None:
        request = _request()
        request["task"]["repository"] = 42
        with self.assertRaises(PortableInvestigationError):
            investigate_run(request, _records())

    def test_run_sources_requested_evidence_and_competing_ledger_are_bound(
        self,
    ) -> None:
        mismatched_source = _request()
        mismatched_source["run_sources"][0]["source_type"] = "claude-code"
        with self.assertRaises(PortableInvestigationError):
            investigate_run(mismatched_source, _records())

        test_request = _request()
        test_request["requested_evidence"] = ["test_execution"]
        authorization_request = _request()
        authorization_request["requested_evidence"] = ["authorization"]
        test_result = investigate_run(test_request, _records())
        authorization_result = investigate_run(
            authorization_request,
            _records(),
        )
        self.assertNotEqual(
            test_result["evidence_candidates"],
            authorization_result["evidence_candidates"],
        )
        self.assertTrue(
            any(
                item["candidate_type"]
                in {"tool_observation", "command_observation", "counter_evidence"}
                for item in test_result["evidence_candidates"]
            )
        )
        self.assertFalse(
            any(
                item["candidate_type"]
                in {"tool_observation", "command_observation", "counter_evidence"}
                for item in authorization_result["evidence_candidates"]
            )
        )

        competing_refs = {
            entry["hypothesis_ref"]
            for entry in test_result["ledger"]
            if entry["effect"] == "supports_competing"
        }
        self.assertTrue(competing_refs)
        self.assertNotIn("competing:recorded-failure", competing_refs)
        for reference in competing_refs:
            prefix, _, index = reference.partition(":")
            self.assertEqual("competing", prefix)
            self.assertTrue(index.isdigit())
            self.assertIn(
                int(index),
                {0, len(test_request["hypotheses"]["competing"])},
            )

    def test_run_source_requires_meta_even_when_other_record_spoofs_type(
        self,
    ) -> None:
        records = [
            copy.deepcopy(record)
            for record in _records()
            if record["record_type"] != "meta"
        ]
        records[0]["source_type"] = "codex"
        with self.assertRaises(PortableInvestigationError):
            investigate_run(_request(), records)

    def test_result_preserves_request_and_record_source_bindings(self) -> None:
        request = _request()
        records = _records()
        result = investigate_run(request, records)

        self.assertEqual(
            request["requested_evidence"],
            result["requested_evidence"],
        )
        self.assertEqual(request["run_sources"], result["run_sources"])

        source_type_by_group = {
            source["run_group_id"]: source["source_type"]
            for source in request["run_sources"]
        }
        expected = [
            {
                "id": record["record_id"],
                "run_group_id": record["source_identity"]["run_group_id"],
                "identity_kind": record["source_identity"]["identity_kind"],
                "content_hash": record["source_identity"]["content_hash"],
                "source_type": source_type_by_group[
                    record["source_identity"]["run_group_id"]
                ],
                "schema_version": record["schema_version"],
            }
            for record in records
        ]
        self.assertEqual(expected, result["record_sources"])

    def test_canonical_record_hashes_reject_stale_identity_after_mutation(
        self,
    ) -> None:
        records = _records()
        baseline = investigate_run(_request(), records)
        self.assertEqual(
            len(records),
            baseline["usage"]["run_records_read"],
        )

        def mutate_record(
            values: list[dict[str, Any]],
            record_type: str,
            field: str,
            replacement: str,
        ) -> None:
            record = next(
                item
                for item in values
                if item["record_type"] == record_type
            )
            original_identity = copy.deepcopy(record["source_identity"])
            record[field] = replacement
            self.assertEqual(original_identity, record["source_identity"])

        mutations = {
            "content": lambda values: mutate_record(
                values,
                "user",
                "content",
                "Tampered user content.",
            ),
            "arguments": lambda values: mutate_record(
                values,
                "tool_call",
                "arguments_json",
                '{"command":["pytest","tests/tampered"]}',
            ),
            "result": lambda values: mutate_record(
                values,
                "tool_result",
                "result_text",
                "tampered result: 99 passed",
            ),
            "top_level_record_id": lambda values: mutate_record(
                values,
                "user",
                "record_id",
                "record-user-tampered",
            ),
        }
        for name, mutate in mutations.items():
            with self.subTest(tampered_field=name):
                tampered = copy.deepcopy(records)
                mutate(tampered)
                with self.assertRaises(PortableInvestigationError):
                    investigate_run(_request(), tampered)

    def test_canonical_record_fixture_uses_sha256_identifiers(self) -> None:
        def is_lowercase_sha256(value: Any) -> bool:
            return (
                isinstance(value, str)
                and len(value) == 64
                and all(
                    character in "0123456789abcdef"
                    for character in value
                )
            )

        records = _records()
        for record in records:
            with self.subTest(record_id=record["record_id"]):
                identity = record["source_identity"]
                self.assertTrue(is_lowercase_sha256(record["record_id"]))
                self.assertEqual(
                    record["record_id"],
                    identity["record_id"],
                )
                self.assertTrue(
                    is_lowercase_sha256(identity["content_hash"])
                )
                linked = record.get("linked_tool_call_record_id")
                if linked is not None:
                    self.assertTrue(is_lowercase_sha256(linked))

    def test_canonical_record_links_and_ids_fail_closed_on_forgery(
        self,
    ) -> None:
        baseline = _records()

        def cross_link_failed_result(
            values: list[dict[str, Any]],
        ) -> None:
            pass_call = next(
                item
                for item in values
                if item["record_type"] == "tool_call"
                and item["tool_call_id"] == "call-auth-pass"
            )
            failed_result = next(
                item
                for item in values
                if item["record_type"] == "tool_result"
                and item["tool_call_id"] == "call-auth-fail"
            )
            failed_result["linked_tool_call_record_id"] = pass_call[
                "record_id"
            ]

        def forge_link_format(values: list[dict[str, Any]]) -> None:
            result = next(
                item
                for item in values
                if item["record_type"] == "tool_result"
            )
            result["linked_tool_call_record_id"] = "not-a-sha256"

        def forge_matching_record_ids(
            values: list[dict[str, Any]],
        ) -> None:
            record = next(
                item
                for item in values
                if item["record_type"] == "user"
            )
            record["record_id"] = "matching-but-not-a-sha256"
            record["source_identity"]["record_id"] = (
                "matching-but-not-a-sha256"
            )

        mutations = {
            "mismatched_tool_call_id": cross_link_failed_result,
            "non_sha256_link": forge_link_format,
            "matching_non_sha256_record_ids": forge_matching_record_ids,
        }
        for name, mutate in mutations.items():
            with self.subTest(forgery=name):
                records = copy.deepcopy(baseline)
                mutate(records)
                with self.assertRaises(PortableInvestigationError):
                    investigate_run(_request(), records)

    def test_writer_rejects_hidden_counter_evidence_references(self) -> None:
        baseline = investigate_run(_request(), _records())
        counter_refs = [
            item["id"]
            for item in baseline["evidence_candidates"]
            if item["candidate_type"] == "counter_evidence"
        ]
        self.assertTrue(counter_refs)
        mutations = {
            "disconfirming_search": lambda value: value[
                "disconfirming_search"
            ].update({"counter_evidence_candidate_refs": []}),
            "finding": lambda value: value["findings"][0].update(
                {"counter_evidence_candidate_refs": []}
            ),
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, mutate in mutations.items():
                with self.subTest(hidden_from=name):
                    result = copy.deepcopy(baseline)
                    mutate(result)
                    output = root / f"hidden-counter-{name}.json"
                    with self.assertRaises(PortableInvestigationError):
                        write_investigation_result(result, output)
                    self.assertFalse(output.exists())

    def test_writer_requires_every_searched_record_in_read_ledger(self) -> None:
        result = investigate_run(_request(), _records())
        self.assertTrue(
            any(
                entry["action"] == "read_run_record"
                for entry in result["ledger"]
            )
        )
        result["ledger"] = [
            entry
            for entry in result["ledger"]
            if entry["action"] != "read_run_record"
        ]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "missing-read-ledger.json"
            with self.assertRaises(PortableInvestigationError):
                write_investigation_result(result, output)
            self.assertFalse(output.exists())

    def test_writer_rejects_forged_sources_and_ledger_inputs(self) -> None:
        baseline = investigate_run(_request(), _records())

        def forge_observation_source(value: dict[str, Any]) -> None:
            value["observations"][0]["source_refs"] = [
                "record-forged-001"
            ]

        def forge_candidate_source(value: dict[str, Any]) -> None:
            value["evidence_candidates"][0]["source_refs"] = [
                "record-forged-001"
            ]

        def forge_ledger_input(value: dict[str, Any]) -> None:
            entry = next(
                item
                for item in value["ledger"]
                if item["action"] == "record_observation"
            )
            entry["input_refs"] = ["record-forged-001"]

        mutations = {
            "observation_source": forge_observation_source,
            "candidate_source": forge_candidate_source,
            "ledger_input": forge_ledger_input,
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, mutate in mutations.items():
                with self.subTest(forgery=name):
                    result = copy.deepcopy(baseline)
                    mutate(result)
                    output = root / f"forged-{name}.json"
                    with self.assertRaises(PortableInvestigationError):
                        write_investigation_result(result, output)
                    self.assertFalse(output.exists())

    def test_policy_extensions_nested_tuple_secret_fails_closed(self) -> None:
        request = _request()
        request["policy"]["extensions"] = {
            "nested": ("token=fixture-secret-value",)
        }
        before = copy.deepcopy(request)
        with self.assertRaises(PortableInvestigationError):
            investigate_run(request, _records())
        self.assertEqual(before, request)


if __name__ == "__main__":
    unittest.main()
