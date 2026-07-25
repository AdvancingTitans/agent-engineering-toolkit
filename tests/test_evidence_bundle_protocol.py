from __future__ import annotations

import hashlib
import json
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aet.bundle import (
    BundleError,
    canonical_json_bytes,
    load_bundle,
    manifest_content_hash,
    render_bundle_markdown,
    validate_bundle,
)


FIXTURES = Path(__file__).parent / "fixtures" / "evidence-bundles"
MINIMAL = FIXTURES / "minimal"
EVIDENCE_SCHEMA = (
    Path(__file__).parent.parent
    / "schemas"
    / "evidence-bundle"
    / "v1"
    / "evidence.schema.json"
)
LEDGER_ENTRY_SCHEMA = (
    Path(__file__).parent.parent
    / "schemas"
    / "evidence-bundle"
    / "v1"
    / "ledger-entry.schema.json"
)
MANIFEST_SCHEMA = (
    Path(__file__).parent.parent
    / "schemas"
    / "evidence-bundle"
    / "v1"
    / "manifest.schema.json"
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"测试 Fixture 必须是 JSON 对象：{path}")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise AssertionError(f"测试 Fixture 的 JSONL 行必须是对象：{path}")
        values.append(value)
    return values


def _write_jsonl(path: Path, values: list[dict[str, Any]]) -> None:
    content = "".join(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n"
        for value in values
    )
    path.write_text(content, encoding="utf-8")


def _copy_minimal(parent: Path, name: str) -> Path:
    destination = parent / name
    shutil.copytree(MINIMAL, destination)
    return destination


def _bundle_projection_data(bundle: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    return {
        "manifest": manifest,
        "claims": _read_jsonl(bundle / "core" / "claims.jsonl"),
        "evidence": _read_jsonl(bundle / "core" / "evidence.jsonl"),
        "observations": _read_jsonl(bundle / "core" / "observations.jsonl"),
    }


def _reseal(bundle: Path, *, render_report: bool = True) -> None:
    manifest_path = bundle / "manifest.json"
    manifest = _read_json(manifest_path)
    if render_report:
        (bundle / "report.md").write_text(
            render_bundle_markdown(_bundle_projection_data(bundle, manifest)),
            encoding="utf-8",
        )
    relative_paths = set(manifest["contents"].values())
    blobs = bundle / "blobs"
    if blobs.is_dir():
        relative_paths.update(
            path.relative_to(bundle).as_posix()
            for path in blobs.rglob("*")
            if path.is_file() and not path.is_symlink()
        )
    file_hashes = {
        relative: hashlib.sha256((bundle / relative).read_bytes()).hexdigest()
        for relative in sorted(relative_paths)
    }
    manifest["integrity"]["file_hashes"] = file_hashes
    manifest["bundle"]["content_hash"] = manifest_content_hash(manifest)
    _write_json(manifest_path, manifest)


def _make_conflicted(bundle: Path) -> None:
    claims = _read_jsonl(bundle / "core" / "claims.jsonl")
    claims[0].update(
        {
            "status": "conflicted",
            "status_definition": "支持证据与相关反证尚未得到解决。",
            "counter_evidence_refs": ["ev-002"],
            "basis": {
                "type": "mixed",
                "explanation": "当前验证结果与后续工作区变化同时存在。",
            },
            "limitations": ["相关文件已在验证后发生变化。"],
            "smallest_next_action": "在当前工作区重新执行声明的验证命令。",
        }
    )
    _write_jsonl(bundle / "core" / "claims.jsonl", claims)

    evidence = _read_jsonl(bundle / "core" / "evidence.jsonl")
    evidence.append(
        {
            "id": "ev-002",
            "proposition": "相关文件在验证命令完成后发生变化。",
            "kind": "freshness_fact",
            "strength": "corroborated",
            "strength_definition": "文件哈希与历史证据绑定不一致。",
            "source_refs": ["src-002"],
            "bindings": {
                "task_id": "task-fixture-001",
                "workspace_id": "workspace-fixture-001",
                "paths": ["tests/test_example.py"],
            },
            "freshness": {
                "status": "current",
                "checked_at": "2026-01-02T03:05:00Z",
                "explanation": "该变化事实由当前工作区重新检查。",
                "effect": "历史测试结果不能证明当前工作区通过。",
            },
            "supports": [],
            "contradicts": ["claim-001"],
            "limitations": [],
            "integrity": {
                "content_hash": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd",
                "truncated": False,
            },
        }
    )
    _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)

    sources = _read_jsonl(bundle / "archive" / "sources.jsonl")
    sources.append(
        {
            "id": "src-002",
            "type": "file",
            "locator": {
                "repository": "https://example.invalid/sanitized/repository",
                "commit": "0123456789abcdef0123456789abcdef01234567",
                "path": "tests/test_example.py",
            },
            "provenance": {
                "source_type": "deterministic_runtime",
                "schema_version": "1.0",
            },
            "integrity": {
                "content_hash": "dddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddddd"
            },
        }
    )
    _write_jsonl(bundle / "archive" / "sources.jsonl", sources)

    conflicts = [
        {
            "id": "conflict-001",
            "proposition": "历史验证结果是否适用于当前工作区。",
            "evidence_refs": ["ev-001", "ev-002"],
            "conflict_type": "workspace_conflict",
            "resolution_status": "unresolved",
            "explanation": "验证成功后相关文件发生变化。",
        }
    ]
    _write_jsonl(bundle / "archive" / "conflicts.jsonl", conflicts)

    index = _read_json(bundle / "index.json")
    index["evidence_refs"] = ["ev-001", "ev-002"]
    _write_json(bundle / "index.json", index)
    _reseal(bundle)


def _make_unknown(bundle: Path) -> None:
    claims = _read_jsonl(bundle / "core" / "claims.jsonl")
    claims[0].update(
        {
            "status": "unknown",
            "status_definition": "现有证据不足以确定当前工作区是否通过验证。",
            "basis": {
                "type": "observational",
                "explanation": "只有历史观察，缺少当前工作区时效确认。",
            },
            "limitations": ["当前工作区时效状态未知。"],
            "smallest_next_action": "检查证据时效或重新执行验证命令。",
        }
    )
    _write_jsonl(bundle / "core" / "claims.jsonl", claims)
    evidence = _read_jsonl(bundle / "core" / "evidence.jsonl")
    evidence[0]["freshness"] = {
        "status": "unknown",
        "explanation": "无法读取当前工作区绑定。",
        "effect": "历史结果不能作为当前工作区证明。",
        "recommended_action": "恢复工作区访问后重新检查时效。",
    }
    _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)
    _reseal(bundle)


def _make_stale(bundle: Path) -> None:
    claims = _read_jsonl(bundle / "core" / "claims.jsonl")
    claims[0].update(
        {
            "status": "partially_supported",
            "status_definition": "历史执行得到支持，但不能证明当前工作区状态。",
            "basis": {
                "type": "observational",
                "explanation": "历史验证存在，但当前工作区时效已经失效。",
            },
            "limitations": ["相关文件在证据产生后发生变化。"],
            "smallest_next_action": "重新执行受影响的验证命令。",
        }
    )
    _write_jsonl(bundle / "core" / "claims.jsonl", claims)
    evidence = _read_jsonl(bundle / "core" / "evidence.jsonl")
    evidence[0]["freshness"] = {
        "status": "relevant_files_changed",
        "checked_at": "2026-01-02T03:06:00Z",
        "explanation": "声明为相关的测试文件在证据产生后发生变化。",
        "effect": "历史退出码仍然有效，但不能证明当前工作区通过。",
        "recommended_action": "重新执行声明的验证命令。",
    }
    _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)
    _reseal(bundle)


def _make_truncated(bundle: Path) -> Path:
    raw = "前置输出\n完整结果：1 项通过\n".encode()
    digest = hashlib.sha256(raw).hexdigest()
    blobs = bundle / "blobs"
    blobs.mkdir()
    blob = blobs / f"sha256-{digest}"
    blob.write_bytes(raw)

    evidence = _read_jsonl(bundle / "core" / "evidence.jsonl")
    evidence[0]["strength"] = "observed"
    evidence[0]["strength_definition"] = "执行记录包含被截断的工具输出。"
    evidence[0]["integrity"] = {
        "content_hash": digest,
        "blob_ref": f"blobs/sha256-{digest}",
        "truncated": True,
        "original_bytes": len(raw),
    }
    evidence[0]["limitations"] = ["模型视图被截断，完整内容保存在 Blob 中。"]
    _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)

    diagnostics = [
        {
            "code": "truncated_tool_output",
            "severity": "warning",
            "effect": "模型视图不能被视为完整工具输出。",
            "affected_observation_refs": ["obs-001"],
            "affected_evidence_refs": ["ev-001"],
            "recommended_action": "读取完整 Blob 或重新执行命令。",
        }
    ]
    _write_jsonl(bundle / "archive" / "diagnostics.jsonl", diagnostics)

    claims = _read_jsonl(bundle / "core" / "claims.jsonl")
    claims[0].update(
        {
            "status": "partially_supported",
            "status_definition": "记录支持历史观察，但模型视图不完整。",
            "basis": {
                "type": "observational",
                "explanation": "完整输出可通过内容寻址 Blob 按需读取。",
            },
            "limitations": ["默认模型视图被截断。"],
            "smallest_next_action": "读取完整 Blob 后再决定是否需要重跑。",
        }
    )
    _write_jsonl(bundle / "core" / "claims.jsonl", claims)
    policy = _read_json(bundle / "policy.json")
    policy["privacy_policy"]["export_raw_tool_output"] = True
    _write_json(bundle / "policy.json", policy)
    _reseal(bundle)
    return blob


def _set_policy_overlap(bundle: Path) -> None:
    policy = _read_json(bundle / "policy.json")
    policy["denied_tools"].append(policy["allowed_tools"][0])
    _write_json(bundle / "policy.json", policy)


def _attach_evidence_blob(
    bundle: Path,
    raw: bytes,
    *,
    include_original_bytes: bool,
    allow_export: bool,
) -> Path:
    digest = hashlib.sha256(raw).hexdigest()
    blobs = bundle / "blobs"
    blobs.mkdir(exist_ok=True)
    blob = blobs / f"sha256-{digest}"
    blob.write_bytes(raw)

    evidence = _read_jsonl(bundle / "core" / "evidence.jsonl")
    evidence[0]["integrity"] = {
        "content_hash": digest,
        "blob_ref": f"blobs/sha256-{digest}",
        "truncated": False,
    }
    if include_original_bytes:
        evidence[0]["integrity"]["original_bytes"] = len(raw)
    _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)

    policy = _read_json(bundle / "policy.json")
    policy["privacy_policy"]["export_raw_tool_output"] = allow_export
    _write_json(bundle / "policy.json", policy)
    _reseal(bundle)
    return blob


class EvidenceBundleProtocolTests(unittest.TestCase):
    def test_canonical_json_is_utf8_sorted_compact_and_deterministic(self) -> None:
        first = {"β": 2, "list": [2, 1], "a": {"z": 2, "x": 1}}
        second = {"a": {"x": 1, "z": 2}, "list": [2, 1], "β": 2}
        expected = '{"a":{"x":1,"z":2},"list":[2,1],"β":2}'.encode()
        self.assertEqual(expected, canonical_json_bytes(first))
        self.assertEqual(expected, canonical_json_bytes(second))
        self.assertEqual(
            hashlib.sha256(canonical_json_bytes(first)).hexdigest(),
            hashlib.sha256(canonical_json_bytes(second)).hexdigest(),
        )

    def test_minimal_fixture_loads_and_validates(self) -> None:
        loaded = load_bundle(MINIMAL)
        validated = validate_bundle(MINIMAL)
        for value in (loaded, validated):
            self.assertEqual("bundle-fixture-001", value["manifest"]["bundle"]["id"])
            self.assertEqual(["claim-001"], [item["id"] for item in value["claims"]])
            self.assertEqual(["ev-001"], [item["id"] for item in value["evidence"]])
            self.assertEqual(["obs-001"], [item["id"] for item in value["observations"]])
            self.assertEqual({}, value["blobs"])
            self.assertIn("结构化来源", value["consumer_guide"])
        manifest = validated["manifest"]
        self.assertEqual(
            manifest["bundle"]["content_hash"],
            manifest_content_hash(manifest),
        )

    def test_conflicted_unknown_stale_and_truncated_cases_validate(self) -> None:
        scenarios = {
            item["id"]: item
            for item in _read_json(FIXTURES / "scenarios.json")["cases"]
        }
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, mutate in (
                ("conflicted", _make_conflicted),
                ("unknown", _make_unknown),
                ("stale", _make_stale),
                ("truncated", _make_truncated),
            ):
                with self.subTest(case=name):
                    bundle = _copy_minimal(root, name)
                    mutate(bundle)
                    loaded = validate_bundle(bundle)
                    self.assertEqual(
                        scenarios[name]["claim_status"],
                        loaded["claims"][0]["status"],
                    )
                    self.assertEqual(
                        scenarios[name]["freshness_status"],
                        loaded["evidence"][0]["freshness"]["status"],
                    )
                    self.assertEqual(
                        scenarios[name]["truncated"],
                        loaded["evidence"][0]["integrity"]["truncated"],
                    )
                    if scenarios[name]["requires_counter_evidence"]:
                        self.assertTrue(loaded["claims"][0]["counter_evidence_refs"])
                        self.assertTrue(loaded["conflicts"])
                    if name == "truncated":
                        self.assertEqual(1, len(loaded["blobs"]))
                        self.assertEqual(
                            loaded["evidence"][0]["integrity"]["original_bytes"],
                            len(next(iter(loaded["blobs"].values()))),
                        )

    def test_tampered_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "tampered-file")
            report = bundle / "report.md"
            report.write_text(report.read_text(encoding="utf-8") + "\n篡改内容\n", encoding="utf-8")
            with self.assertRaises(BundleError):
                validate_bundle(bundle)

    def test_manifest_semantics_are_bound_without_self_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "tampered-manifest")
            manifest = _read_json(bundle / "manifest.json")
            manifest["task"]["request"] = "被改写的任务"
            _write_json(bundle / "manifest.json", manifest)
            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("integrity_error", captured.exception.code)

    def test_resealed_markdown_cannot_strengthen_claims(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "strengthened-report")
            (bundle / "report.md").write_text("所有功能已证明安全。\n", encoding="utf-8")
            _reseal(bundle, render_report=False)
            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("projection_error", captured.exception.code)

    def test_tampered_blob_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "tampered-blob")
            blob = _make_truncated(bundle)
            blob.write_bytes(blob.read_bytes() + b"tampered")
            with self.assertRaises(BundleError):
                validate_bundle(bundle)

    def test_missing_reference_is_rejected_after_valid_reseal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "missing-reference")
            claims = _read_jsonl(bundle / "core" / "claims.jsonl")
            claims[0]["observation_refs"] = ["obs-missing"]
            _write_jsonl(bundle / "core" / "claims.jsonl", claims)
            _reseal(bundle)
            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("reference_error", captured.exception.code)

    def test_deleting_counter_evidence_is_rejected_after_valid_reseal(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "deleted-counter")
            _make_conflicted(bundle)
            evidence = [
                item
                for item in _read_jsonl(bundle / "core" / "evidence.jsonl")
                if item["id"] != "ev-002"
            ]
            _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)
            _reseal(bundle)
            with self.assertRaises(BundleError):
                validate_bundle(bundle)

    def test_conflicted_claim_cannot_hide_all_counter_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "hidden-counter")
            _make_conflicted(bundle)
            claims = _read_jsonl(bundle / "core" / "claims.jsonl")
            claims[0]["counter_evidence_refs"] = []
            _write_jsonl(bundle / "core" / "claims.jsonl", claims)
            evidence = [
                item
                for item in _read_jsonl(bundle / "core" / "evidence.jsonl")
                if item["id"] != "ev-002"
            ]
            _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)
            index = _read_json(bundle / "index.json")
            index["evidence_refs"] = ["ev-001"]
            _write_json(bundle / "index.json", index)
            _write_jsonl(bundle / "archive" / "conflicts.jsonl", [])
            _reseal(bundle)
            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("counter_evidence_error", captured.exception.code)

    def test_truncated_evidence_requires_a_complete_bound_blob(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing = _copy_minimal(root, "missing-blob")
            evidence = _read_jsonl(missing / "core" / "evidence.jsonl")
            evidence[0]["integrity"]["truncated"] = True
            _write_jsonl(missing / "core" / "evidence.jsonl", evidence)
            _reseal(missing)
            with self.assertRaises(BundleError):
                validate_bundle(missing)

            mismatched = _copy_minimal(root, "mismatched-blob")
            _make_truncated(mismatched)
            evidence = _read_jsonl(mismatched / "core" / "evidence.jsonl")
            evidence[0]["integrity"]["content_hash"] = "0" * 64
            _write_jsonl(mismatched / "core" / "evidence.jsonl", evidence)
            _reseal(mismatched)
            with self.assertRaises(BundleError) as captured:
                validate_bundle(mismatched)
            self.assertEqual("integrity_error", captured.exception.code)

    def test_index_policy_guide_and_ledger_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            cases = (
                (
                    "index",
                    lambda path: _write_json(
                        path / "index.json",
                        {
                            **_read_json(path / "index.json"),
                            "evidence_refs": [],
                        },
                    ),
                ),
                (
                    "guide",
                    lambda path: (path / "consumer-guide.md").write_text("", encoding="utf-8"),
                ),
                (
                    "policy",
                    lambda path: _set_policy_overlap(path),
                ),
                (
                    "ledger",
                    lambda path: _write_jsonl(path / "archive" / "ledger.jsonl", [{}]),
                ),
            )
            for name, mutate in cases:
                with self.subTest(case=name):
                    bundle = _copy_minimal(root, name)
                    mutate(bundle)
                    _reseal(bundle)
                    with self.assertRaises(BundleError):
                        validate_bundle(bundle)

    def test_unknown_enum_is_rejected_as_unsupported_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "unknown-enum")
            evidence = _read_jsonl(bundle / "core" / "evidence.jsonl")
            evidence[0]["strength"] = "trusted"
            _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)
            _reseal(bundle)
            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("unsupported_semantics", captured.exception.code)

    def test_symbolic_linked_bundle_file_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            bundle = _copy_minimal(root, "symbolic-link")
            outside = root / "outside-report.md"
            outside.write_bytes((bundle / "report.md").read_bytes())
            (bundle / "report.md").unlink()
            (bundle / "report.md").symlink_to(outside)
            with self.assertRaises(BundleError):
                validate_bundle(bundle)

    def test_run_observation_cannot_claim_reproduced_strength(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "run-observation-reproduced")
            evidence = _read_jsonl(bundle / "core" / "evidence.jsonl")
            evidence[0]["kind"] = "run_observation"
            _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("grounding_error", captured.exception.code)

    def test_context_only_evidence_cannot_support_supported_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "context-only-supported")
            evidence = _read_jsonl(bundle / "core" / "evidence.jsonl")
            evidence[0]["strength"] = "context_only"
            _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)
            claims = _read_jsonl(bundle / "core" / "claims.jsonl")
            claims[0]["basis"] = {
                "type": "observational",
                "explanation": "仅有上下文材料，未达到可支持结论的证据强度。",
            }
            _write_jsonl(bundle / "core" / "claims.jsonl", claims)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("grounding_error", captured.exception.code)

    def test_stale_evidence_cannot_support_supported_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "stale-supported")
            evidence = _read_jsonl(bundle / "core" / "evidence.jsonl")
            evidence[0]["freshness"] = {
                "status": "relevant_files_changed",
                "checked_at": "2026-01-02T03:06:00Z",
                "explanation": "相关文件在证据产生后发生变化。",
                "effect": "历史结果不能证明当前工作区状态。",
                "recommended_action": "重新执行验证命令。",
            }
            _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)
            claims = _read_jsonl(bundle / "core" / "claims.jsonl")
            claims[0]["basis"] = {
                "type": "observational",
                "explanation": "历史执行记录已经过期。",
            }
            _write_jsonl(bundle / "core" / "claims.jsonl", claims)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("grounding_error", captured.exception.code)

    def test_execution_is_rejected_when_policy_disallows_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "execution-forbidden")
            ledger = _read_jsonl(bundle / "archive" / "ledger.jsonl")
            ledger[0]["action"] = "execute_authorized_command"
            _write_jsonl(bundle / "archive" / "ledger.jsonl", ledger)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("policy_error", captured.exception.code)

    def test_tool_budget_cannot_be_evaded_by_omitting_tool_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "missing-tool-name")
            ledger = _read_jsonl(bundle / "archive" / "ledger.jsonl")
            ledger[0].pop("tool_name")
            _write_jsonl(bundle / "archive" / "ledger.jsonl", ledger)
            policy = _read_json(bundle / "policy.json")
            policy["budgets"]["max_tool_calls"] = 0
            _write_json(bundle / "policy.json", policy)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("policy_error", captured.exception.code)

    def test_ledger_rejects_missing_observation_input_and_output_targets(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            mutations = {
                "observation": lambda entry: entry.update(
                    {"observation_refs": ["obs-missing"]}
                ),
                "input": lambda entry: entry.update({"input_ref": "src-missing"}),
                "output": lambda entry: entry.update({"output_ref": "ev-missing"}),
            }
            for name, mutate in mutations.items():
                with self.subTest(reference=name):
                    bundle = _copy_minimal(root, f"missing-ledger-{name}")
                    ledger = _read_jsonl(bundle / "archive" / "ledger.jsonl")
                    mutate(ledger[0])
                    _write_jsonl(bundle / "archive" / "ledger.jsonl", ledger)
                    _reseal(bundle)

                    with self.assertRaises(BundleError) as captured:
                        validate_bundle(bundle)
                    self.assertEqual("reference_error", captured.exception.code)

    def test_resolved_conflict_cannot_support_conflicted_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "resolved-conflict")
            _make_conflicted(bundle)
            conflicts = _read_jsonl(bundle / "archive" / "conflicts.jsonl")
            conflicts[0]["resolution_status"] = "resolved"
            _write_jsonl(bundle / "archive" / "conflicts.jsonl", conflicts)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("counter_evidence_error", captured.exception.code)

    def test_source_blob_hash_mismatch_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "source-blob-mismatch")
            raw = b"source payload"
            digest = hashlib.sha256(raw).hexdigest()
            blobs = bundle / "blobs"
            blobs.mkdir()
            (blobs / f"sha256-{digest}").write_bytes(raw)
            sources = _read_jsonl(bundle / "archive" / "sources.jsonl")
            sources[0]["locator"]["blob_ref"] = f"blobs/sha256-{digest}"
            sources[0]["integrity"]["content_hash"] = "0" * 64
            _write_jsonl(bundle / "archive" / "sources.jsonl", sources)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("integrity_error", captured.exception.code)

    def test_non_truncated_blob_original_bytes_is_optional_in_schema_and_runtime(
        self,
    ) -> None:
        schema = _read_json(EVIDENCE_SCHEMA)
        integrity_schema = schema["properties"]["integrity"]
        self.assertNotIn("original_bytes", integrity_schema["required"])
        truncated_requirements = schema["allOf"][0]["then"]["properties"]["integrity"][
            "required"
        ]
        self.assertIn("original_bytes", truncated_requirements)

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for include_original_bytes in (False, True):
                with self.subTest(include_original_bytes=include_original_bytes):
                    bundle = _copy_minimal(
                        root,
                        f"non-truncated-{include_original_bytes}",
                    )
                    _attach_evidence_blob(
                        bundle,
                        b"complete command output",
                        include_original_bytes=include_original_bytes,
                        allow_export=True,
                    )
                    validated = validate_bundle(bundle)
                    integrity = validated["evidence"][0]["integrity"]
                    self.assertEqual(
                        include_original_bytes,
                        "original_bytes" in integrity,
                    )

    def test_export_reasoning_false_rejects_reasoning_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "reasoning-forbidden")
            observations = _read_jsonl(bundle / "core" / "observations.jsonl")
            observations[0]["type"] = "agent_reasoning"
            _write_jsonl(bundle / "core" / "observations.jsonl", observations)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("privacy_error", captured.exception.code)

    def test_export_raw_tool_output_false_rejects_command_output_blob(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "raw-output-forbidden")
            _attach_evidence_blob(
                bundle,
                b"raw command output",
                include_original_bytes=False,
                allow_export=False,
            )

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("privacy_error", captured.exception.code)

    def test_consumer_blob_limit_is_independent_from_policy_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "consumer-blob-budget")
            blob = _make_truncated(bundle)
            blob_bytes = blob.stat().st_size
            policy = _read_json(bundle / "policy.json")
            self.assertGreater(
                policy["budgets"]["max_blob_bytes_read"],
                blob_bytes,
            )

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle, max_blob_bytes=blob_bytes - 1)
            self.assertEqual("budget_error", captured.exception.code)
            self.assertEqual(
                "bundle-fixture-001",
                validate_bundle(bundle, max_blob_bytes=blob_bytes)["manifest"][
                    "bundle"
                ]["id"],
            )

    def test_candidate_budget_counts_unique_candidate_references(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "unique-candidate-budget")
            ledger = _read_jsonl(bundle / "archive" / "ledger.jsonl")
            ledger[0]["evidence_candidate_refs"] = ["candidate-001"]
            ledger.append(
                {
                    "id": "ledger-002",
                    "timestamp": "2026-01-02T03:04:06Z",
                    "question": "是否需要验证同一证据候选？",
                    "hypothesis_ref": "primary",
                    "action": "propose_candidate",
                    "observation_refs": ["obs-001"],
                    "evidence_candidate_refs": ["candidate-001"],
                    "effect": "no_change",
                    "explanation": "重复引用同一候选不应重复消耗候选预算。",
                }
            )
            _write_jsonl(bundle / "archive" / "ledger.jsonl", ledger)
            policy = _read_json(bundle / "policy.json")
            policy["budgets"]["max_evidence_candidates"] = 1
            _write_json(bundle / "policy.json", policy)
            _reseal(bundle)
            validate_bundle(bundle)

            ledger[1]["evidence_candidate_refs"].append("candidate-002")
            _write_jsonl(bundle / "archive" / "ledger.jsonl", ledger)
            _reseal(bundle)
            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("budget_error", captured.exception.code)

    def test_read_file_rejects_denied_and_outside_allowed_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, path in (
                ("denied", ".git/config"),
                ("outside-allowed", "src/aet/bundle/validator.py"),
            ):
                with self.subTest(path_policy=name):
                    bundle = _copy_minimal(root, f"read-file-{name}")
                    sources = _read_jsonl(bundle / "archive" / "sources.jsonl")
                    sources[0]["locator"]["path"] = path
                    _write_jsonl(bundle / "archive" / "sources.jsonl", sources)

                    ledger = _read_jsonl(bundle / "archive" / "ledger.jsonl")
                    ledger[0].update(
                        {
                            "action": "read_file",
                            "tool_name": "file.read",
                            "input_ref": "src-001",
                        }
                    )
                    _write_jsonl(bundle / "archive" / "ledger.jsonl", ledger)

                    policy = _read_json(bundle / "policy.json")
                    policy["allowed_tools"].append("file.read")
                    _write_json(bundle / "policy.json", policy)
                    _reseal(bundle)

                    with self.assertRaises(BundleError) as captured:
                        validate_bundle(bundle)
                    self.assertEqual("policy_error", captured.exception.code)

    def test_read_run_record_requires_input_ref_even_with_zero_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "read-run-without-input")
            ledger = _read_jsonl(bundle / "archive" / "ledger.jsonl")
            ledger[0]["action"] = "read_run_record"
            ledger[0].pop("input_ref", None)
            _write_jsonl(bundle / "archive" / "ledger.jsonl", ledger)
            policy = _read_json(bundle / "policy.json")
            policy["budgets"]["max_run_records_read"] = 0
            _write_json(bundle / "policy.json", policy)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("invalid_bundle", captured.exception.code)

    def test_read_run_record_rejects_proof_tool_and_source_budget_bypass(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(
                Path(temporary),
                "read-run-proof-budget-bypass",
            )
            ledger = _read_jsonl(bundle / "archive" / "ledger.jsonl")
            ledger[0].update(
                {
                    "action": "read_run_record",
                    "tool_name": "proof.inspect",
                    "input_ref": "src-001",
                }
            )
            _write_jsonl(bundle / "archive" / "ledger.jsonl", ledger)

            policy = _read_json(bundle / "policy.json")
            policy["budgets"]["max_run_records_read"] = 0
            _write_json(bundle / "policy.json", policy)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("policy_error", captured.exception.code)

    def test_propose_candidate_requires_reference_even_with_zero_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "candidate-without-reference")
            ledger = _read_jsonl(bundle / "archive" / "ledger.jsonl")
            ledger[0]["action"] = "propose_candidate"
            ledger[0]["evidence_candidate_refs"] = []
            ledger[0].pop("tool_name", None)
            _write_jsonl(bundle / "archive" / "ledger.jsonl", ledger)
            policy = _read_json(bundle / "policy.json")
            policy["budgets"]["max_evidence_candidates"] = 0
            _write_json(bundle / "policy.json", policy)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("invalid_bundle", captured.exception.code)

    def test_disconfirming_search_cannot_be_faked_by_record_observation(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "fake-disconfirming-search")
            ledger = _read_jsonl(bundle / "archive" / "ledger.jsonl")
            ledger[0].update(
                {
                    "action": "record_observation",
                    "effect": "weakens_primary",
                }
            )
            ledger[0].pop("tool_name", None)
            _write_jsonl(bundle / "archive" / "ledger.jsonl", ledger)
            policy = _read_json(bundle / "policy.json")
            policy["require_disconfirming_search"] = True
            _write_json(bundle / "policy.json", policy)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("policy_error", captured.exception.code)

    def test_non_ascii_hypothesis_ref_is_rejected_by_schema_and_runtime(self) -> None:
        schema = _read_json(LEDGER_ENTRY_SCHEMA)
        pattern = schema["properties"]["hypothesis_ref"]["pattern"]
        self.assertEqual(
            "^(primary|competing:[A-Za-z0-9._-]+)$",
            pattern,
        )
        self.assertIsNone(re.fullmatch(pattern, "competing:竞争"))

        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "non-ascii-hypothesis")
            ledger = _read_jsonl(bundle / "archive" / "ledger.jsonl")
            ledger[0]["hypothesis_ref"] = "competing:竞争"
            _write_jsonl(bundle / "archive" / "ledger.jsonl", ledger)
            _reseal(bundle)

            with self.assertRaises(BundleError) as captured:
                validate_bundle(bundle)
            self.assertEqual("invalid_bundle", captured.exception.code)

    def test_bundle_timestamps_require_utc_in_schema_and_runtime(self) -> None:
        manifest_schema = _read_json(MANIFEST_SCHEMA)
        evidence_schema = _read_json(EVIDENCE_SCHEMA)
        ledger_schema = _read_json(LEDGER_ENTRY_SCHEMA)
        timestamp_patterns = {
            "manifest.created_at": manifest_schema["properties"]["bundle"][
                "properties"
            ]["created_at"]["pattern"],
            "evidence.freshness.checked_at": evidence_schema["$defs"]["freshness"][
                "properties"
            ]["checked_at"]["pattern"],
            "ledger.timestamp": ledger_schema["properties"]["timestamp"]["pattern"],
        }
        for label, pattern in timestamp_patterns.items():
            with self.subTest(schema_timestamp=label):
                self.assertEqual("(Z|\\+00:00)$", pattern)
                self.assertIsNone(re.search(pattern, "2026-01-02T11:04:05+08:00"))

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            runtime_cases = {
                "manifest.created_at": lambda bundle: self._set_non_utc_manifest(
                    bundle
                ),
                "evidence.freshness.checked_at": lambda bundle: (
                    self._set_non_utc_evidence(bundle)
                ),
                "ledger.timestamp": lambda bundle: self._set_non_utc_ledger(bundle),
            }
            for label, mutate in runtime_cases.items():
                with self.subTest(runtime_timestamp=label):
                    bundle = _copy_minimal(
                        root,
                        f"non-utc-{label.replace('.', '-')}",
                    )
                    mutate(bundle)
                    _reseal(bundle)
                    with self.assertRaises(BundleError) as captured:
                        validate_bundle(bundle)
                    self.assertEqual("invalid_bundle", captured.exception.code)

    @staticmethod
    def _set_non_utc_manifest(bundle: Path) -> None:
        manifest = _read_json(bundle / "manifest.json")
        manifest["bundle"]["created_at"] = "2026-01-02T11:04:05+08:00"
        _write_json(bundle / "manifest.json", manifest)

    @staticmethod
    def _set_non_utc_evidence(bundle: Path) -> None:
        evidence = _read_jsonl(bundle / "core" / "evidence.jsonl")
        evidence[0]["freshness"]["checked_at"] = "2026-01-02T11:04:05+08:00"
        _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)

    @staticmethod
    def _set_non_utc_ledger(bundle: Path) -> None:
        ledger = _read_jsonl(bundle / "archive" / "ledger.jsonl")
        ledger[0]["timestamp"] = "2026-01-02T11:04:05+08:00"
        _write_jsonl(bundle / "archive" / "ledger.jsonl", ledger)


if __name__ == "__main__":
    unittest.main()
