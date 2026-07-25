from __future__ import annotations

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aet.bundle import (
    BundleError,
    compile_bundle,
    render_bundle_markdown,
    validate_bundle,
)


MINIMAL = (
    Path(__file__).parent / "fixtures" / "evidence-bundles" / "minimal"
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AssertionError(f"Fixture 必须包含 JSON 对象：{path}")
    return value


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    values: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        value = json.loads(line)
        if not isinstance(value, dict):
            raise AssertionError(f"Fixture JSONL 行必须是对象：{path}")
        values.append(value)
    return values


def _minimal_payload() -> dict[str, Any]:
    manifest = _read_json(MINIMAL / "manifest.json")
    index = _read_json(MINIMAL / "index.json")
    blobs: dict[str, bytes] = {}
    blob_root = MINIMAL / "blobs"
    if blob_root.is_dir():
        blobs = {
            path.relative_to(MINIMAL).as_posix(): path.read_bytes()
            for path in blob_root.iterdir()
            if path.is_file()
        }
    return {
        "bundle_id": manifest["bundle"]["id"],
        "created_at": manifest["bundle"]["created_at"],
        "producer_version": manifest["producer"]["version"],
        "task": copy.deepcopy(manifest["task"]),
        "investigation": copy.deepcopy(manifest["investigation"]),
        "claims": _read_jsonl(MINIMAL / "core" / "claims.jsonl"),
        "evidence": _read_jsonl(MINIMAL / "core" / "evidence.jsonl"),
        "observations": _read_jsonl(
            MINIMAL / "core" / "observations.jsonl"
        ),
        "sources": _read_jsonl(MINIMAL / "archive" / "sources.jsonl"),
        "diagnostics": _read_jsonl(
            MINIMAL / "archive" / "diagnostics.jsonl"
        ),
        "conflicts": _read_jsonl(
            MINIMAL / "archive" / "conflicts.jsonl"
        ),
        "ledger": _read_jsonl(MINIMAL / "archive" / "ledger.jsonl"),
        "policy": _read_json(MINIMAL / "policy.json"),
        "blobs": blobs,
        "consumer_guidance": copy.deepcopy(index["consumer_guidance"]),
        "excluded_reason": index["excluded"]["reason"],
    }


def _add_second_claim_closure(payload: dict[str, Any]) -> None:
    claim = copy.deepcopy(payload["claims"][0])
    claim.update(
        {
            "id": "claim-002",
            "statement": "第二项独立验证命题。",
            "evidence_refs": ["ev-002"],
            "observation_refs": ["obs-002"],
        }
    )
    payload["claims"].append(claim)

    evidence = copy.deepcopy(payload["evidence"][0])
    evidence.update(
        {
            "id": "ev-002",
            "proposition": "第二项验证命令成功执行。",
            "source_refs": ["src-002"],
            "supports": ["claim-002"],
        }
    )
    payload["evidence"].append(evidence)

    observation = copy.deepcopy(payload["observations"][0])
    observation.update(
        {
            "id": "obs-002",
            "statement": "执行记录包含第二项验证结果。",
            "source_refs": ["src-002"],
        }
    )
    payload["observations"].append(observation)

    source = copy.deepcopy(payload["sources"][0])
    source["id"] = "src-002"
    source["locator"]["path"] = "reports/second-proof.json"
    payload["sources"].append(source)

    ledger = copy.deepcopy(payload["ledger"][0])
    ledger.update(
        {
            "id": "ledger-002",
            "timestamp": "2026-01-02T03:04:06Z",
            "observation_refs": ["obs-002"],
            "output_ref": "ev-002",
        }
    )
    payload["ledger"].append(ledger)


def _bind_blob(
    payload: dict[str, Any],
    raw: bytes,
    *,
    reference: str | None = None,
) -> str:
    digest = hashlib.sha256(raw).hexdigest()
    blob_ref = reference or f"blobs/sha256-{digest}"
    payload["blobs"][blob_ref] = raw
    payload["evidence"][0]["integrity"] = {
        "content_hash": digest,
        "blob_ref": blob_ref,
        "truncated": False,
        "original_bytes": len(raw),
    }
    payload["policy"]["privacy_policy"]["export_raw_tool_output"] = True
    return blob_ref


def _directory_snapshot(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


class EvidenceBundleCompilerTests(unittest.TestCase):
    def test_valid_payload_compiles_and_validates(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            compiled = compile_bundle(_minimal_payload(), output)
            validated = validate_bundle(output)
            self.assertEqual(
                "bundle-fixture-001",
                compiled["manifest"]["bundle"]["id"],
            )
            self.assertEqual(compiled["manifest"], validated["manifest"])
            self.assertEqual(["claim-001"], validated["index"]["claim_refs"])

    def test_claim_slice_keeps_reference_closure_and_reports_excluded(self) -> None:
        payload = _minimal_payload()
        _add_second_claim_closure(payload)
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            compiled = compile_bundle(
                payload,
                output,
                claim_refs=["claim-001"],
            )

            self.assertEqual(["claim-001"], compiled["index"]["claim_refs"])
            self.assertEqual(["ev-001"], compiled["index"]["evidence_refs"])
            self.assertEqual(["obs-001"], compiled["index"]["observation_refs"])
            self.assertEqual(
                5,
                compiled["index"]["excluded"]["count"],
            )
            self.assertTrue(compiled["index"]["excluded"]["reason"])
            serialized = json.dumps(
                {
                    name: compiled[name]
                    for name in (
                        "claims",
                        "evidence",
                        "observations",
                        "sources",
                        "diagnostics",
                        "conflicts",
                        "ledger",
                    )
                },
                ensure_ascii=False,
            )
            for excluded_id in (
                "claim-002",
                "ev-002",
                "obs-002",
                "src-002",
                "ledger-002",
            ):
                self.assertNotIn(excluded_id, serialized)

    def test_compilation_does_not_mutate_input_or_historical_evidence(self) -> None:
        payload = _minimal_payload()
        before = copy.deepcopy(payload)
        historical_command = copy.deepcopy(
            payload["evidence"][0]["bindings"]["command"]
        )
        historical_freshness = copy.deepcopy(
            payload["evidence"][0]["freshness"]
        )

        with tempfile.TemporaryDirectory() as temporary:
            compile_bundle(payload, Path(temporary) / "bundle")

        self.assertEqual(before, payload)
        self.assertEqual(
            historical_command,
            payload["evidence"][0]["bindings"]["command"],
        )
        self.assertEqual(
            historical_freshness,
            payload["evidence"][0]["freshness"],
        )

    def test_same_payload_produces_identical_directory_bytes(self) -> None:
        payload = _minimal_payload()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = root / "first"
            second = root / "second"
            compile_bundle(payload, first)
            compile_bundle(copy.deepcopy(payload), second)
            self.assertEqual(
                _directory_snapshot(first),
                _directory_snapshot(second),
            )

    def test_existing_output_is_rejected_without_changes(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            output.mkdir()
            sentinel = output / "sentinel.txt"
            sentinel.write_text("保留", encoding="utf-8")
            with self.assertRaises(BundleError) as captured:
                compile_bundle(_minimal_payload(), output)
            self.assertEqual("output_exists", captured.exception.code)
            self.assertEqual("保留", sentinel.read_text(encoding="utf-8"))

    def test_validation_failure_leaves_no_target_or_temporary_directory(self) -> None:
        payload = _minimal_payload()
        payload["created_at"] = "2026-01-02T11:04:05+08:00"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "bundle"
            with self.assertRaises(BundleError):
                compile_bundle(payload, output)
            self.assertFalse(output.exists())
            self.assertFalse(
                any(path.name.startswith(".bundle.") for path in root.iterdir())
            )

    def test_blob_content_address_is_verified_before_publication(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            valid_payload = _minimal_payload()
            raw = b"complete deterministic proof output"
            reference = _bind_blob(valid_payload, raw)
            compiled = compile_bundle(valid_payload, root / "valid")
            self.assertEqual(raw, compiled["blobs"][reference])
            self.assertEqual(
                reference.removeprefix("blobs/sha256-"),
                hashlib.sha256(compiled["blobs"][reference]).hexdigest(),
            )

            invalid_payload = _minimal_payload()
            _bind_blob(
                invalid_payload,
                raw,
                reference="blobs/sha256-" + ("0" * 64),
            )
            invalid_output = root / "invalid"
            with self.assertRaises(BundleError) as captured:
                compile_bundle(invalid_payload, invalid_output)
            self.assertEqual("integrity_error", captured.exception.code)
            self.assertFalse(invalid_output.exists())

    def test_secret_redaction_derives_text_and_blob_hashes(self) -> None:
        secret = "fixture-secret-value"
        raw = f"token={secret}\nverification complete\n".encode()
        payload = _minimal_payload()
        original_reference = _bind_blob(payload, raw)
        payload["claims"][0]["statement"] = f"命题包含 token={secret}"
        payload["evidence"][0]["proposition"] = (
            f"证据包含 authorization=Bearer-{secret}"
        )
        payload["observations"][0]["statement"] = (
            f"观察包含 password={secret}"
        )
        before = copy.deepcopy(payload)

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            compiled = compile_bundle(payload, output)
            redacted_evidence = compiled["evidence"][0]
            new_reference = redacted_evidence["integrity"]["blob_ref"]
            new_blob = compiled["blobs"][new_reference]

            self.assertNotEqual(original_reference, new_reference)
            self.assertNotEqual(raw, new_blob)
            self.assertEqual(
                new_reference,
                "blobs/sha256-" + hashlib.sha256(new_blob).hexdigest(),
            )
            self.assertEqual(
                hashlib.sha256(new_blob).hexdigest(),
                redacted_evidence["integrity"]["content_hash"],
            )
            self.assertEqual(
                len(new_blob),
                redacted_evidence["integrity"]["original_bytes"],
            )
            exported = b"".join(_directory_snapshot(output).values())
            self.assertNotIn(secret.encode(), exported)
            self.assertIn(b"[REDACTED]", exported)
            self.assertEqual(before, payload)

    def test_raw_output_policy_fails_closed_and_publishes_nothing(self) -> None:
        payload = _minimal_payload()
        _bind_blob(payload, b"raw command output")
        payload["policy"]["privacy_policy"]["redact_secrets"] = False
        payload["policy"]["privacy_policy"]["export_raw_tool_output"] = False

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            with self.assertRaises(BundleError) as captured:
                compile_bundle(payload, output)
            self.assertEqual("privacy_error", captured.exception.code)
            self.assertFalse(output.exists())

    def test_markdown_is_deterministic_projection_of_compiled_json(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            compiled = compile_bundle(_minimal_payload(), output)
            expected = render_bundle_markdown(
                {
                    "manifest": compiled["manifest"],
                    "claims": compiled["claims"],
                }
            )
            self.assertEqual(expected, compiled["report"])
            self.assertEqual(
                expected,
                (output / "report.md").read_text(encoding="utf-8"),
            )
            for claim in compiled["claims"]:
                self.assertIn(claim["id"], expected)
                self.assertIn(claim["statement"], expected)

    def test_missing_reference_fails_closed_without_output(self) -> None:
        payload = _minimal_payload()
        payload["claims"][0]["evidence_refs"] = ["ev-missing"]
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            with self.assertRaises(BundleError) as captured:
                compile_bundle(payload, output)
            self.assertEqual("reference_error", captured.exception.code)
            self.assertFalse(output.exists())

    def test_reverse_counter_evidence_cannot_be_silently_excluded(self) -> None:
        payload = _minimal_payload()
        counter = copy.deepcopy(payload["evidence"][0])
        counter.update(
            {
                "id": "ev-counter-001",
                "proposition": "反向记录显示目标命题存在失败结果。",
                "source_refs": ["src-counter-001"],
                "supports": [],
                "contradicts": ["claim-001"],
            }
        )
        payload["evidence"].append(counter)
        source = copy.deepcopy(payload["sources"][0])
        source["id"] = "src-counter-001"
        source["locator"]["path"] = "reports/counter-proof.json"
        payload["sources"].append(source)
        self.assertEqual([], payload["claims"][0]["counter_evidence_refs"])

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            with self.assertRaises(BundleError) as captured:
                compile_bundle(payload, output, claim_refs=["claim-001"])
            self.assertEqual("counter_evidence_error", captured.exception.code)
            self.assertFalse(output.exists())

    def test_blob_owned_only_by_excluded_claim_is_not_exported(self) -> None:
        payload = _minimal_payload()
        _add_second_claim_closure(payload)
        raw = b"second claim private proof output"
        digest = hashlib.sha256(raw).hexdigest()
        reference = f"blobs/sha256-{digest}"
        payload["blobs"][reference] = raw
        payload["evidence"][1]["integrity"] = {
            "content_hash": digest,
            "blob_ref": reference,
            "truncated": False,
            "original_bytes": len(raw),
        }
        payload["policy"]["privacy_policy"]["export_raw_tool_output"] = True

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            compiled = compile_bundle(
                payload,
                output,
                claim_refs=["claim-001"],
            )
            self.assertEqual({}, compiled["blobs"])
            self.assertNotIn(reference, compiled["manifest"]["integrity"]["file_hashes"])
            self.assertFalse((output / reference).exists())

    def test_non_utf8_blob_fails_closed_when_secret_redaction_is_required(
        self,
    ) -> None:
        payload = _minimal_payload()
        _bind_blob(payload, b"token=fixture-secret-value\xff")
        self.assertTrue(
            payload["policy"]["privacy_policy"]["redact_secrets"]
        )

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            with self.assertRaises(BundleError) as captured:
                compile_bundle(payload, output)
            self.assertEqual("privacy_error", captured.exception.code)
            self.assertFalse(output.exists())

    def test_source_blob_redaction_updates_locator_and_integrity_together(
        self,
    ) -> None:
        payload = _minimal_payload()
        raw = b"token=fixture-secret-value\nsource proof\n"
        digest = hashlib.sha256(raw).hexdigest()
        old_reference = f"blobs/sha256-{digest}"
        payload["blobs"][old_reference] = raw
        payload["sources"][0]["locator"]["blob_ref"] = old_reference
        payload["sources"][0]["integrity"]["content_hash"] = digest

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            compiled = compile_bundle(payload, output)
            source = compiled["sources"][0]
            new_reference = source["locator"]["blob_ref"]
            new_blob = compiled["blobs"][new_reference]
            new_digest = hashlib.sha256(new_blob).hexdigest()

            self.assertNotEqual(old_reference, new_reference)
            self.assertEqual(
                f"blobs/sha256-{new_digest}",
                new_reference,
            )
            self.assertEqual(
                new_digest,
                source["integrity"]["content_hash"],
            )
            self.assertNotIn(b"fixture-secret-value", new_blob)
            validate_bundle(output)

    def test_secret_in_stable_reference_field_fails_closed(self) -> None:
        payload = _minimal_payload()
        payload["ledger"][0]["output_ref"] = "token=fixture-secret-value"
        self.assertTrue(
            payload["policy"]["privacy_policy"]["redact_secrets"]
        )

        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "bundle"
            with self.assertRaises(BundleError) as captured:
                compile_bundle(payload, output)
            self.assertEqual("privacy_error", captured.exception.code)
            self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
