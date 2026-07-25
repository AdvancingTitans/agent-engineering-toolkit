from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aet.run_normalization import NormalizationError, normalize_run, write_normalized_run


FIXTURES = Path(__file__).parent / "fixtures" / "run-normalization"
SOURCES = ("codex", "claude-code")
RECORD_TYPES = {
    "meta",
    "user",
    "assistant",
    "reasoning",
    "tool_call",
    "tool_result",
}
IDENTITY_KEYS = {
    "run_group_id",
    "stable_source_record_id",
    "identity_kind",
    "source_order_id",
    "record_id",
    "content_hash",
}


def _records(result: dict[str, Any], record_type: str) -> list[dict[str, Any]]:
    return [
        record
        for record in result["records"]
        if record["record_type"] == record_type
    ]


def _diagnostic_codes(result: dict[str, Any]) -> set[str]:
    return {diagnostic["code"] for diagnostic in result["diagnostics"]}


def _write_lines(path: Path, values: list[dict[str, Any] | str]) -> None:
    lines = [
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        for value in values
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


class RunNormalizationTests(unittest.TestCase):
    def test_each_adapter_emits_all_six_record_types_with_stable_shape(self) -> None:
        for source in SOURCES:
            with self.subTest(source=source):
                result = normalize_run(
                    source,
                    FIXTURES / source / "complete.jsonl",
                    run_group_id=f"run-group-{source}",
                    generation_id="generation-fixture-001",
                )
                self.assertEqual(
                    {"schema_version", "manifest", "records", "diagnostics"},
                    set(result),
                )
                self.assertEqual("agent-run-normalization/1.0", result["schema_version"])
                self.assertEqual(RECORD_TYPES, {item["record_type"] for item in result["records"]})
                self.assertEqual(len(result["records"]), result["manifest"]["record_count"])
                self.assertEqual(
                    len(result["diagnostics"]),
                    result["manifest"]["diagnostic_count"],
                )
                self.assertEqual(source, result["manifest"]["source_type"])
                self.assertEqual(f"run-group-{source}", result["manifest"]["run_group_id"])
                self.assertEqual(
                    "generation-fixture-001",
                    result["manifest"]["generation_id"],
                )
                self.assertFalse(result["manifest"]["partial"])
                self.assertEqual(0, result["manifest"]["base_byte_offset"])
                self.assertTrue(result["manifest"]["provenance"])

                for record in result["records"]:
                    self.assertEqual(
                        {"record_type", "record_id", "source_identity"}
                        | ({"source_type"} if record["record_type"] == "meta" else set()),
                        {"record_type", "record_id", "source_identity"}
                        | ({"source_type"} if "source_type" in record else set()),
                    )
                    self.assertEqual(IDENTITY_KEYS, set(record["source_identity"]))
                    self.assertEqual(record["record_id"], record["source_identity"]["record_id"])
                    self.assertEqual(
                        f"run-group-{source}",
                        record["source_identity"]["run_group_id"],
                    )

                meta = _records(result, "meta")
                self.assertEqual(1, len(meta))
                self.assertEqual("synthetic", meta[0]["source_identity"]["identity_kind"])
                reasoning = _records(result, "reasoning")
                self.assertEqual(1, len(reasoning))
                self.assertFalse(reasoning[0]["public_export_allowed"])
                call = _records(result, "tool_call")[0]
                tool_result = _records(result, "tool_result")[0]
                self.assertEqual(call["tool_call_id"], tool_result["tool_call_id"])
                self.assertEqual(call["record_id"], tool_result["linked_tool_call_record_id"])

    def test_native_location_content_and_synthetic_identity_levels_are_explicit(self) -> None:
        complete = normalize_run(
            "codex",
            FIXTURES / "codex" / "complete.jsonl",
            run_group_id="run-group-identities",
            generation_id="generation-identities",
        )
        kinds = {
            record["source_identity"]["identity_kind"]
            for record in complete["records"]
        }
        self.assertIn("synthetic", kinds)
        self.assertIn("native", kinds)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            no_native = root / "no-native.jsonl"
            _write_lines(
                no_native,
                [{
                    "type": "response_item",
                    "timestamp": "2026-01-02T03:04:01Z",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": "无原生 ID 的合成消息。",
                    },
                }],
            )
            located = normalize_run(
                "codex",
                no_native,
                run_group_id="run-group-identities",
                generation_id="generation-identities",
            )
            self.assertEqual(
                "location",
                _records(located, "user")[0]["source_identity"]["identity_kind"],
            )
            content = normalize_run(
                "codex",
                no_native,
                run_group_id="run-group-identities",
                partial=True,
            )
            self.assertEqual(
                "content",
                _records(content, "user")[0]["source_identity"]["identity_kind"],
            )
            self.assertIn("content_identity_fallback", _diagnostic_codes(content))
            self.assertIn("partial_run", _diagnostic_codes(content))

    def test_normalization_is_deterministic_for_fixed_input_and_context(self) -> None:
        for source in SOURCES:
            with self.subTest(source=source):
                arguments = {
                    "run_group_id": f"run-group-{source}",
                    "generation_id": "generation-deterministic",
                }
                first = normalize_run(
                    source,
                    FIXTURES / source / "complete.jsonl",
                    **arguments,
                )
                second = normalize_run(
                    source,
                    FIXTURES / source / "complete.jsonl",
                    **arguments,
                )
                self.assertEqual(first, second)
                self.assertEqual(
                    [item["record_id"] for item in first["records"]],
                    [item["record_id"] for item in second["records"]],
                )

    def test_diagnostics_cover_declared_fail_closed_cases_without_source_text(self) -> None:
        required = {
            "malformed_record",
            "unsupported_record",
            "invalid_timestamp",
            "truncated_tool_output",
            "repaired_record",
            "orphan_tool_result",
            "duplicate_tool_result",
            "missing_tool_result",
        }
        for source in SOURCES:
            with self.subTest(source=source):
                result = normalize_run(
                    source,
                    FIXTURES / source / "diagnostics.jsonl",
                    run_group_id=f"run-group-diagnostics-{source}",
                    generation_id="generation-diagnostics",
                )
                self.assertTrue(required <= _diagnostic_codes(result))
                diagnostics_text = json.dumps(
                    result["diagnostics"],
                    ensure_ascii=False,
                    sort_keys=True,
                )
                self.assertNotIn("此内容不应进入诊断消息", diagnostics_text)
                for diagnostic in result["diagnostics"]:
                    self.assertEqual(
                        {"code", "severity", "message"}
                        | ({"input_location"} if "input_location" in diagnostic else set())
                        | ({"count"} if "count" in diagnostic else set()),
                        set(diagnostic),
                    )
                    if "input_location" in diagnostic:
                        self.assertTrue(
                            set(diagnostic["input_location"])
                            <= {"line", "byte_offset", "record_index"}
                        )

    def test_diagnostics_never_echo_a_secret_from_unsupported_input(self) -> None:
        marker = "secret-fixture-never-diagnostic"
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "secret.jsonl"
            _write_lines(
                source,
                [{
                    "type": "unsupported_event",
                    "payload": {"content": marker},
                }],
            )
            result = normalize_run(
                "codex",
                source,
                run_group_id="run-group-secret",
                generation_id="generation-secret",
            )
            self.assertIn("unsupported_record", _diagnostic_codes(result))
            self.assertNotIn(
                marker,
                json.dumps(result["diagnostics"], ensure_ascii=False),
            )

    def test_full_and_chunked_imports_keep_the_same_record_ids(self) -> None:
        for source in SOURCES:
            with self.subTest(source=source), tempfile.TemporaryDirectory() as temporary:
                raw = (FIXTURES / source / "complete.jsonl").read_bytes()
                lines = raw.splitlines(keepends=True)
                split_at = max(2, len(lines) // 2)
                first_bytes = b"".join(lines[:split_at])
                second_bytes = b"".join(lines[split_at:])
                root = Path(temporary)
                first_path = root / "chunk-1.jsonl"
                second_path = root / "chunk-2.jsonl"
                first_path.write_bytes(first_bytes)
                second_path.write_bytes(second_bytes)
                context = {
                    "run_group_id": f"run-group-chunked-{source}",
                    "generation_id": "generation-chunked",
                }
                full = normalize_run(
                    source,
                    FIXTURES / source / "complete.jsonl",
                    **context,
                )
                first = normalize_run(
                    source,
                    first_path,
                    partial=True,
                    **context,
                )
                merged = normalize_run(
                    source,
                    second_path,
                    base_byte_offset=len(first_bytes),
                    prior=first,
                    **context,
                )
                self.assertEqual(
                    [record["record_id"] for record in full["records"]],
                    [record["record_id"] for record in merged["records"]],
                )

    def test_reimporting_the_same_chunk_is_idempotent(self) -> None:
        first = normalize_run(
            "codex",
            FIXTURES / "codex" / "chunk-1.jsonl",
            run_group_id="run-group-idempotent",
            generation_id="generation-idempotent",
            partial=True,
        )
        repeated = normalize_run(
            "codex",
            FIXTURES / "codex" / "chunk-1.jsonl",
            run_group_id="run-group-idempotent",
            generation_id="generation-idempotent",
            partial=True,
            prior=first,
        )
        self.assertEqual(
            [record["record_id"] for record in first["records"]],
            [record["record_id"] for record in repeated["records"]],
        )
        self.assertEqual(len(repeated["records"]), len({
            record["record_id"] for record in repeated["records"]
        }))
        self.assertEqual(
            len(repeated["diagnostics"]),
            len({
                json.dumps(item, ensure_ascii=False, sort_keys=True)
                for item in repeated["diagnostics"]
            }),
        )

    def test_tool_result_links_across_chunks_for_both_adapters(self) -> None:
        for source in SOURCES:
            with self.subTest(source=source):
                first_path = FIXTURES / source / "chunk-1.jsonl"
                second_path = FIXTURES / source / "chunk-2.jsonl"
                context = {
                    "run_group_id": f"run-group-link-{source}",
                    "generation_id": "generation-link",
                }
                first = normalize_run(
                    source,
                    first_path,
                    partial=True,
                    **context,
                )
                merged = normalize_run(
                    source,
                    second_path,
                    base_byte_offset=len(first_path.read_bytes()),
                    prior=first,
                    **context,
                )
                call = _records(merged, "tool_call")[0]
                tool_result = _records(merged, "tool_result")[0]
                self.assertEqual(call["tool_call_id"], tool_result["tool_call_id"])
                self.assertEqual(call["record_id"], tool_result["linked_tool_call_record_id"])
                self.assertNotIn("orphan_tool_result", _diagnostic_codes(merged))
                self.assertNotIn("missing_tool_result", _diagnostic_codes(merged))

    def test_same_native_identity_with_changed_content_is_a_conflict(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first_path = root / "first.jsonl"
            changed_path = root / "changed.jsonl"
            base = {
                "type": "response_item",
                "timestamp": "2026-01-02T03:04:01Z",
                "payload": {
                    "id": "stable-message-001",
                    "type": "message",
                    "role": "user",
                    "content": "第一版内容。",
                },
            }
            _write_lines(first_path, [base])
            changed = json.loads(json.dumps(base, ensure_ascii=False))
            changed["payload"]["content"] = "同一身份的不同内容。"
            _write_lines(changed_path, [changed])
            prior = normalize_run(
                "codex",
                first_path,
                run_group_id="run-group-conflict",
                generation_id="generation-conflict",
                partial=True,
            )
            with self.assertRaises(NormalizationError):
                normalize_run(
                    "codex",
                    changed_path,
                    run_group_id="run-group-conflict",
                    generation_id="generation-conflict",
                    partial=True,
                    prior=prior,
                )

    def test_generation_changes_record_ids_and_prior_cannot_cross_generations(self) -> None:
        path = FIXTURES / "codex" / "complete.jsonl"
        first = normalize_run(
            "codex",
            path,
            run_group_id="run-group-generations",
            generation_id="generation-a",
        )
        replacement = normalize_run(
            "codex",
            path,
            run_group_id="run-group-generations",
            generation_id="generation-b",
        )
        self.assertEqual("generation-a", first["manifest"]["generation_id"])
        self.assertEqual("generation-b", replacement["manifest"]["generation_id"])
        self.assertNotEqual(
            [record["record_id"] for record in first["records"]],
            [record["record_id"] for record in replacement["records"]],
        )
        with self.assertRaises(NormalizationError):
            normalize_run(
                "codex",
                path,
                run_group_id="run-group-generations",
                generation_id="generation-b",
                prior=first,
            )
        defaulted = normalize_run(
            "codex",
            path,
            run_group_id="run-group-generations-default",
        )
        self.assertEqual("generation-0", defaulted["manifest"]["generation_id"])

    def test_partial_run_defers_missing_tool_result_until_final_import(self) -> None:
        path = FIXTURES / "codex" / "chunk-1.jsonl"
        partial = normalize_run(
            "codex",
            path,
            run_group_id="run-group-missing",
            generation_id="generation-missing",
            partial=True,
        )
        self.assertNotIn("missing_tool_result", _diagnostic_codes(partial))
        complete = normalize_run(
            "codex",
            path,
            run_group_id="run-group-missing",
            generation_id="generation-missing",
        )
        self.assertIn("missing_tool_result", _diagnostic_codes(complete))

    def test_write_normalized_run_emits_three_deterministic_files(self) -> None:
        result = normalize_run(
            "codex",
            FIXTURES / "codex" / "complete.jsonl",
            run_group_id="run-group-write",
            generation_id="generation-write",
        )
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "normalized"
            self.assertEqual(output, write_normalized_run(result, output))
            self.assertEqual(
                {"manifest.json", "records.jsonl", "diagnostics.jsonl"},
                {path.name for path in output.iterdir()},
            )
            self.assertEqual(
                result["manifest"],
                json.loads((output / "manifest.json").read_text(encoding="utf-8")),
            )
            written_records = [
                json.loads(line)
                for line in (output / "records.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertEqual(result["records"], written_records)
            before = {
                path.name: path.read_bytes()
                for path in output.iterdir()
            }
            self.assertEqual(output, write_normalized_run(result, output))
            self.assertEqual(
                before,
                {path.name: path.read_bytes() for path in output.iterdir()},
            )

    def test_unknown_source_and_invalid_offsets_fail_closed(self) -> None:
        path = FIXTURES / "codex" / "complete.jsonl"
        with self.assertRaises(NormalizationError):
            normalize_run("unknown-source", path)
        with self.assertRaises(NormalizationError):
            normalize_run("codex", path, base_byte_offset=-1)


if __name__ == "__main__":
    unittest.main()
