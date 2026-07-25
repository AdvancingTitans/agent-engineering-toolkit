from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from aet.bundle import BundleError, validate_review_result

from tests.test_evidence_bundle_protocol import (
    _copy_minimal,
    _make_conflicted,
    _make_stale,
    _make_unknown,
    _read_json,
    _read_jsonl,
    _reseal,
    _write_json,
    _write_jsonl,
)


def _review(
    *,
    disposition: str = "accept",
    evidence_refs: list[str] | None = None,
    counter_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "protocol": {"name": "portable-review-result", "version": "1.0"},
        "bundle_id": "bundle-fixture-001",
        "conclusions": [
            {
                "id": "review-conclusion-001",
                "statement": "目标验证结论具有声明的证据边界。",
                "disposition": disposition,
                "claim_refs": ["claim-001"],
                "evidence_refs": ["ev-001"] if evidence_refs is None else evidence_refs,
                "counter_evidence_refs": [] if counter_refs is None else counter_refs,
                "reasoning_summary": "结论只引用 Portable Evidence Bundle 中的记录。",
                "limitations": ["不扩展到未声明的验证范围。"],
            }
        ],
        "unresolved_questions": [],
    }


class ReviewValidatorTests(unittest.TestCase):
    def test_valid_supported_review_passes(self) -> None:
        report = validate_review_result(
            Path(__file__).parent / "fixtures" / "evidence-bundles" / "minimal",
            _review(),
        )
        self.assertEqual("PASS", report["status"])
        self.assertEqual(1, report["conclusion_count"])

    def test_bundle_and_record_references_must_exist(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "evidence-bundles" / "minimal"
        for name, mutate in (
            ("bundle", lambda value: value.update({"bundle_id": "missing-bundle"})),
            (
                "claim",
                lambda value: value["conclusions"][0].update(
                    {"claim_refs": ["claim-missing"]}
                ),
            ),
            (
                "evidence",
                lambda value: value["conclusions"][0].update(
                    {"evidence_refs": ["obs-001"]}
                ),
            ),
        ):
            with self.subTest(reference=name):
                review = _review()
                mutate(review)
                with self.assertRaises(BundleError):
                    validate_review_result(fixture, review)

    def test_review_cannot_hide_counter_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "conflicted")
            _make_conflicted(bundle)
            with self.assertRaises(BundleError) as captured:
                validate_review_result(
                    bundle,
                    _review(disposition="request_change"),
                )
            self.assertEqual("counter_evidence_error", captured.exception.code)
            report = validate_review_result(
                bundle,
                _review(
                    disposition="request_change",
                    counter_refs=["ev-002"],
                ),
            )
            self.assertEqual("PASS", report["status"])

    def test_unknown_claim_cannot_be_strengthened(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "unknown")
            _make_unknown(bundle)
            with self.assertRaises(BundleError) as captured:
                validate_review_result(bundle, _review(disposition="accept"))
            self.assertEqual("grounding_error", captured.exception.code)
            report = validate_review_result(
                bundle,
                _review(disposition="request_investigation"),
            )
            self.assertEqual("PASS", report["status"])

    def test_conflicted_or_stale_claim_cannot_support_acceptance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            conflicted = _copy_minimal(root, "conflicted")
            _make_conflicted(conflicted)
            stale = _copy_minimal(root, "stale")
            _make_stale(stale)
            for name, bundle, review in (
                (
                    "conflicted",
                    conflicted,
                    _review(disposition="accept", counter_refs=["ev-002"]),
                ),
                ("stale", stale, _review(disposition="accept")),
            ):
                with self.subTest(case=name):
                    with self.assertRaises(BundleError) as captured:
                        validate_review_result(bundle, review)
                    self.assertEqual("grounding_error", captured.exception.code)

    def test_request_change_requires_current_strong_supporting_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stale = _copy_minimal(root, "stale-request-change")
            _make_stale(stale)
            with self.assertRaises(BundleError) as captured:
                validate_review_result(
                    stale,
                    _review(disposition="request_change"),
                )
            self.assertEqual("grounding_error", captured.exception.code)

    def test_root_extensions_are_optional_but_structured(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "evidence-bundles" / "minimal"
        review = _review()
        review["extensions"] = {"consumer": "fixture"}
        self.assertEqual("PASS", validate_review_result(fixture, review)["status"])
        review["extensions"] = []
        with self.assertRaises(BundleError):
            validate_review_result(fixture, review)

    def test_duplicate_json_keys_and_unknown_fields_fail_closed(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "evidence-bundles" / "minimal"
        with tempfile.TemporaryDirectory() as temporary:
            review_path = Path(temporary) / "review.json"
            review_path.write_text(
                '{"protocol":{"name":"portable-review-result","version":"1.0"},'
                '"bundle_id":"bundle-fixture-001","bundle_id":"other",'
                '"conclusions":[],"unresolved_questions":[]}',
                encoding="utf-8",
            )
            with self.assertRaises(BundleError):
                validate_review_result(fixture, review_path)
        review = _review()
        review["unexpected"] = True
        with self.assertRaises(BundleError):
            validate_review_result(fixture, review)

    def test_review_schema_is_valid_json_and_requires_claim_refs(self) -> None:
        schema = json.loads(
            (
                Path(__file__).parents[1]
                / "schemas"
                / "evidence-bundle"
                / "v1"
                / "review-result.schema.json"
            ).read_text(encoding="utf-8")
        )
        conclusion = schema["properties"]["conclusions"]["items"]
        self.assertEqual(1, conclusion["properties"]["claim_refs"]["minItems"])

    def test_accept_requires_current_strong_evidence_for_each_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            bundle = _copy_minimal(Path(temporary), "two-supported-claims")

            claims = _read_jsonl(bundle / "core" / "claims.jsonl")
            second_claim = dict(claims[0])
            second_claim.update(
                {
                    "id": "claim-002",
                    "statement": "第二项验证结论也具有当前强证据。",
                    "evidence_refs": ["ev-002"],
                }
            )
            claims.append(second_claim)
            _write_jsonl(bundle / "core" / "claims.jsonl", claims)

            evidence = _read_jsonl(bundle / "core" / "evidence.jsonl")
            second_evidence = dict(evidence[0])
            second_evidence.update(
                {
                    "id": "ev-002",
                    "proposition": "第二项验证命令在绑定工作区中成功完成。",
                    "source_refs": ["src-002"],
                    "supports": ["claim-002"],
                }
            )
            evidence.append(second_evidence)
            _write_jsonl(bundle / "core" / "evidence.jsonl", evidence)

            sources = _read_jsonl(bundle / "archive" / "sources.jsonl")
            second_source = dict(sources[0])
            second_source["id"] = "src-002"
            second_source["locator"] = dict(second_source["locator"])
            second_source["locator"]["path"] = "reports/second-proof.json"
            sources.append(second_source)
            _write_jsonl(bundle / "archive" / "sources.jsonl", sources)

            index = _read_json(bundle / "index.json")
            index["claim_refs"].append("claim-002")
            index["evidence_refs"].append("ev-002")
            _write_json(bundle / "index.json", index)
            _reseal(bundle)

            review = _review()
            review["conclusions"][0]["claim_refs"] = [
                "claim-001",
                "claim-002",
            ]
            review["conclusions"][0]["evidence_refs"] = ["ev-001"]
            with self.assertRaises(BundleError) as captured:
                validate_review_result(bundle, review)
            self.assertEqual("grounding_error", captured.exception.code)

    def test_request_change_cannot_drop_supported_claim_evidence(self) -> None:
        fixture = Path(__file__).parent / "fixtures" / "evidence-bundles" / "minimal"
        review = _review(disposition="request_change", evidence_refs=[])
        with self.assertRaises(BundleError) as captured:
            validate_review_result(fixture, review)
        self.assertEqual("grounding_error", captured.exception.code)


if __name__ == "__main__":
    unittest.main()
