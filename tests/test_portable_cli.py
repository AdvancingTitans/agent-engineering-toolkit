from __future__ import annotations

import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any
from unittest.mock import patch

from aet.cli import main

from tests.test_portable_investigation import (
    _request,
    _verification_request,
    _working_directory,
    _write_matching_proof,
)
from tests.test_review_validator import _review


TESTS = Path(__file__).parent
NATIVE_RUN = TESTS / "fixtures" / "run-normalization" / "codex" / "complete.jsonl"
MINIMAL_BUNDLE = TESTS / "fixtures" / "evidence-bundles" / "minimal"


def _call(argv: list[str]) -> tuple[int, str]:
    output = io.StringIO()
    with redirect_stdout(output):
        status = main(argv)
    return status, output.getvalue()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _snapshot(path: Path) -> dict[str, bytes]:
    if path.is_file():
        return {path.name: path.read_bytes()}
    return {
        item.relative_to(path).as_posix(): item.read_bytes()
        for item in sorted(path.rglob("*"))
        if item.is_file()
    }


def _review_for_bundle(bundle: Path) -> dict[str, Any]:
    claim = json.loads(
        next(
            line
            for line in (bundle / "core" / "claims.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
    )
    manifest = json.loads((bundle / "manifest.json").read_text(encoding="utf-8"))
    return {
        "protocol": {
            "name": "portable-review-result",
            "version": "1.0",
        },
        "bundle_id": manifest["bundle"]["id"],
        "conclusions": [
            {
                "id": "review-cli-001",
                "statement": "当前只有运行记录观察，需要确定性补证。",
                "disposition": "request_investigation",
                "claim_refs": [claim["id"]],
                "evidence_refs": [],
                "counter_evidence_refs": [],
                "reasoning_summary": "未知命题不被强化为接受或拒绝。",
                "limitations": ["尚未运行确定性验证工具。"],
                "next_action": "运行授权验证。",
            }
        ],
        "unresolved_questions": ["当前工作区中的测试是否通过？"],
    }


def _pipeline(root: Path) -> dict[str, Path]:
    paths = {
        "normalized": root / "normalized-run",
        "inspection": root / "tool-calls.json",
        "request": root / "request.json",
        "investigation": root / "investigation.json",
        "bundle": root / "bundle",
        "rendered": root / "bundle.md",
        "review": root / "review.json",
    }
    request = _request()
    request["run_sources"][0]["run_group_id"] = "run-cli-001"
    _write_json(paths["request"], request)

    status, _ = _call(
        [
            "run",
            "normalize",
            "--source",
            "codex",
            "--input",
            str(NATIVE_RUN),
            "--output",
            str(paths["normalized"]),
            "--run-group-id",
            "run-cli-001",
            "--generation-id",
            "generation-cli-001",
        ]
    )
    if status != 0:
        raise AssertionError("run normalize 未成功")
    status, _ = _call(
        [
            "run",
            "inspect",
            "--run",
            str(paths["normalized"]),
            "--tool-calls",
            "--format",
            "json",
            "--output",
            str(paths["inspection"]),
        ]
    )
    if status != 0:
        raise AssertionError("run inspect 未成功")
    status, _ = _call(
        [
            "investigate",
            "--request",
            str(paths["request"]),
            "--run",
            str(paths["normalized"]),
            "--output",
            str(paths["investigation"]),
        ]
    )
    if status != 0:
        raise AssertionError("investigate 未成功")
    status, _ = _call(
        [
            "bundle",
            "create",
            "--investigation",
            str(paths["investigation"]),
            "--output",
            str(paths["bundle"]),
            "--bundle-id",
            "bundle-cli-001",
            "--created-at",
            "2026-01-02T03:04:05Z",
        ]
    )
    if status != 0:
        raise AssertionError("bundle create 未成功")
    status, _ = _call(["bundle", "validate", str(paths["bundle"])])
    if status != 0:
        raise AssertionError("bundle validate 未成功")
    status, _ = _call(
        [
            "bundle",
            "render",
            "--bundle",
            str(paths["bundle"]),
            "--format",
            "markdown",
            "--output",
            str(paths["rendered"]),
        ]
    )
    if status != 0:
        raise AssertionError("bundle render 未成功")
    _write_json(paths["review"], _review_for_bundle(paths["bundle"]))
    status, _ = _call(
        [
            "bundle",
            "validate-review",
            "--bundle",
            str(paths["bundle"]),
            "--review",
            str(paths["review"]),
        ]
    )
    if status != 0:
        raise AssertionError("bundle validate-review 未成功")
    return paths


class PortableCliTests(unittest.TestCase):
    def test_complete_ingestion_only_cli_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = _pipeline(Path(temporary))
            inspection = json.loads(
                paths["inspection"].read_text(encoding="utf-8")
            )
            self.assertEqual(
                {"tool_call", "tool_result"},
                {item["record_type"] for item in inspection["records"]},
            )
            investigation = json.loads(
                paths["investigation"].read_text(encoding="utf-8")
            )
            self.assertEqual("unknown", investigation["status"])
            self.assertEqual([], investigation["verified_evidence"])
            manifest = json.loads(
                (paths["bundle"] / "manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual("bundle-cli-001", manifest["bundle"]["id"])
            report = paths["rendered"].read_text(encoding="utf-8")
            self.assertIn("unknown", report)

    def test_cli_compiles_authorized_proof_into_portable_verified_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            normalized = root / "normalized"
            request_path = root / "request.json"
            investigation_path = root / "investigation.json"
            bundle_path = root / "bundle"
            proof = _write_matching_proof(
                root,
                ["python", "-m", "unittest", "tests.test_example"],
            )
            request = _verification_request()
            request["run_sources"][0]["run_group_id"] = "run-cli-proof"
            _write_json(request_path, request)
            status, _ = _call(
                [
                    "run",
                    "normalize",
                    "--source",
                    "codex",
                    "--input",
                    str(NATIVE_RUN),
                    "--output",
                    str(normalized),
                    "--run-group-id",
                    "run-cli-proof",
                ]
            )
            self.assertEqual(0, status)
            with _working_directory(root), patch.dict(
                os.environ,
                {"PATH": f"{root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}"},
            ):
                status, _ = _call(
                    [
                        "investigate",
                        "--request",
                        str(request_path),
                        "--run",
                        str(normalized),
                        "--workspace",
                        str(root),
                        "--proof",
                        str(proof),
                        "--output",
                        str(investigation_path),
                    ]
                )
            self.assertEqual(0, status)
            investigation = json.loads(investigation_path.read_text(encoding="utf-8"))
            self.assertEqual("supported", investigation["status"])
            self.assertEqual(1, len(investigation["verified_evidence"]))
            status, _ = _call(
                [
                    "bundle",
                    "create",
                    "--investigation",
                    str(investigation_path),
                    "--output",
                    str(bundle_path),
                    "--created-at",
                    "2026-01-02T03:04:05Z",
                ]
            )
            self.assertEqual(0, status)
            status, output = _call(["bundle", "validate", str(bundle_path)])
            self.assertEqual(0, status)
            self.assertEqual("PASS", json.loads(output)["status"])

    def test_all_new_cli_writers_reject_existing_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = _pipeline(Path(temporary))
            commands = (
                (
                    "normalize",
                    [
                        "run",
                        "normalize",
                        "--source",
                        "codex",
                        "--input",
                        str(NATIVE_RUN),
                        "--output",
                        str(paths["normalized"]),
                    ],
                    paths["normalized"],
                ),
                (
                    "inspect",
                    [
                        "run",
                        "inspect",
                        "--run",
                        str(paths["normalized"]),
                        "--tool-calls",
                        "--output",
                        str(paths["inspection"]),
                    ],
                    paths["inspection"],
                ),
                (
                    "investigate",
                    [
                        "investigate",
                        "--request",
                        str(paths["request"]),
                        "--run",
                        str(paths["normalized"]),
                        "--output",
                        str(paths["investigation"]),
                    ],
                    paths["investigation"],
                ),
                (
                    "bundle-create",
                    [
                        "bundle",
                        "create",
                        "--investigation",
                        str(paths["investigation"]),
                        "--output",
                        str(paths["bundle"]),
                    ],
                    paths["bundle"],
                ),
                (
                    "bundle-render",
                    [
                        "bundle",
                        "render",
                        "--bundle",
                        str(paths["bundle"]),
                        "--output",
                        str(paths["rendered"]),
                    ],
                    paths["rendered"],
                ),
            )
            for name, argv, output in commands:
                with self.subTest(writer=name):
                    before = _snapshot(output)
                    with self.assertRaises(SystemExit):
                        _call(argv)
                    self.assertEqual(before, _snapshot(output))

    def test_cli_errors_fail_closed_without_partial_outputs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            missing_run = root / "missing-run"
            normalized = root / "normalized"
            with self.assertRaises(SystemExit):
                _call(
                    [
                        "run",
                        "normalize",
                        "--source",
                        "codex",
                        "--input",
                        str(root / "missing.jsonl"),
                        "--output",
                        str(normalized),
                    ]
                )
            self.assertFalse(normalized.exists())

            bad_request = root / "bad-request.json"
            _write_json(bad_request, {"protocol_version": "1.0"})
            investigation = root / "investigation.json"
            with self.assertRaises(SystemExit):
                _call(
                    [
                        "investigate",
                        "--request",
                        str(bad_request),
                        "--run",
                        str(missing_run),
                        "--output",
                        str(investigation),
                    ]
                )
            self.assertFalse(investigation.exists())

            bundle = root / "bundle"
            with self.assertRaises(SystemExit):
                _call(
                    [
                        "bundle",
                        "create",
                        "--investigation",
                        str(bad_request),
                        "--output",
                        str(bundle),
                    ]
                )
            self.assertFalse(bundle.exists())

    def test_legacy_run_init_and_status_parsers_still_execute(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            subprocess.run(
                ["git", "init", "-q"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.email", "fixture@example.invalid"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Fixture"],
                cwd=root,
                check=True,
            )
            intent = root / "aet.intent.json"
            _write_json(
                intent,
                {
                    "intent": "Preserve legacy run parser behavior.",
                    "changed_path_budget": 0,
                    "allowed_paths": [],
                    "required_proofs": [],
                },
            )
            subprocess.run(
                ["git", "add", "aet.intent.json"],
                cwd=root,
                check=True,
            )
            subprocess.run(
                ["git", "commit", "-q", "-m", "fixture"],
                cwd=root,
                check=True,
            )
            run = root / "run.json"
            status_output = root / "status.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(
                    0,
                    _call(
                        [
                            "run",
                            "init",
                            "--intent",
                            "aet.intent.json",
                            "--output",
                            str(run),
                        ]
                    )[0],
                )
                self.assertEqual(
                    0,
                    _call(
                        [
                            "run",
                            "status",
                            "--run",
                            str(run),
                            "--format",
                            "json",
                            "--output",
                            str(status_output),
                        ]
                    )[0],
                )
            finally:
                os.chdir(previous)
            status = json.loads(status_output.read_text(encoding="utf-8"))
            self.assertEqual("aet_run_status", status["report_kind"])

    def test_cli_review_accept_requires_cited_current_strong_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            review_path = Path(temporary) / "review.json"
            review = _review(disposition="accept", evidence_refs=[])
            _write_json(review_path, review)
            with self.assertRaises(SystemExit) as captured:
                _call(
                    [
                        "bundle",
                        "validate-review",
                        "--bundle",
                        str(MINIMAL_BUNDLE),
                        "--review",
                        str(review_path),
                    ]
                )
            self.assertIn("grounding_error", str(captured.exception))

    def test_cli_review_rejects_nested_duplicates_and_conclusion_extensions(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            review_path = root / "review.json"
            valid = _review()
            raw = json.dumps(valid, ensure_ascii=False)
            raw = raw.replace(
                '"disposition": "accept"',
                '"disposition": "accept", "disposition": "unknown"',
                1,
            )
            review_path.write_text(raw, encoding="utf-8")
            with self.assertRaises(SystemExit):
                _call(
                    [
                        "bundle",
                        "validate-review",
                        "--bundle",
                        str(MINIMAL_BUNDLE),
                        "--review",
                        str(review_path),
                    ]
                )

            invalid_extension = _review()
            invalid_extension["conclusions"][0]["extensions"] = {
                "consumer": "fixture"
            }
            _write_json(review_path, invalid_extension)
            with self.assertRaises(SystemExit):
                _call(
                    [
                        "bundle",
                        "validate-review",
                        "--bundle",
                        str(MINIMAL_BUNDLE),
                        "--review",
                        str(review_path),
                    ]
                )

    def test_bundle_create_preserves_investigation_audit_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = _pipeline(Path(temporary))
            investigation = json.loads(
                paths["investigation"].read_text(encoding="utf-8")
            )
            policy = json.loads(
                (paths["bundle"] / "policy.json").read_text(encoding="utf-8")
            )
            ledger = [
                json.loads(line)
                for line in (
                    paths["bundle"] / "archive" / "ledger.jsonl"
                ).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            self.assertTrue(investigation["ledger"])
            self.assertTrue(ledger)
            self.assertTrue(
                policy == investigation["policy"]
                or policy.get("extensions", {}).get(
                    "source_investigation_policy"
                )
                == investigation["policy"]
            )

    def test_bundle_preserves_real_run_source_bindings_and_scope(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            paths = _pipeline(Path(temporary))
            request = json.loads(
                paths["request"].read_text(encoding="utf-8")
            )
            investigation = json.loads(
                paths["investigation"].read_text(encoding="utf-8")
            )
            manifest = json.loads(
                (paths["bundle"] / "manifest.json").read_text(
                    encoding="utf-8"
                )
            )
            sources = [
                json.loads(line)
                for line in (
                    paths["bundle"] / "archive" / "sources.jsonl"
                ).read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]

            self.assertEqual(
                request["requested_evidence"],
                investigation["requested_evidence"],
            )
            self.assertEqual(
                request["run_sources"],
                investigation["run_sources"],
            )
            self.assertEqual(
                request["requested_evidence"],
                manifest["investigation"]["scope"],
            )

            result_bindings = {
                item["id"]: item
                for item in investigation["record_sources"]
            }
            self.assertEqual(
                set(result_bindings),
                {item["id"] for item in sources},
            )
            for source in sources:
                with self.subTest(source_id=source["id"]):
                    binding = result_bindings[source["id"]]
                    self.assertEqual("run_record", source["type"])
                    self.assertEqual(
                        binding["run_group_id"],
                        source["locator"]["run_group_id"],
                    )
                    self.assertEqual(
                        binding["identity_kind"],
                        source["locator"]["identity_kind"],
                    )
                    self.assertEqual(
                        binding["source_type"],
                        source["provenance"]["source_type"],
                    )
                    self.assertEqual(
                        binding["content_hash"],
                        source["integrity"]["content_hash"],
                    )

    def test_bundle_render_rejects_regular_and_dangling_symlinks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            paths = _pipeline(root)

            regular_target = root / "regular-target.md"
            regular_target.write_text("保持不变\n", encoding="utf-8")
            regular_link = root / "regular-link.md"
            regular_link.symlink_to(regular_target)
            with self.assertRaises(SystemExit):
                _call(
                    [
                        "bundle",
                        "render",
                        "--bundle",
                        str(paths["bundle"]),
                        "--output",
                        str(regular_link),
                    ]
                )
            self.assertEqual(
                "保持不变\n",
                regular_target.read_text(encoding="utf-8"),
            )

            dangling_target = root / "dangling-target.md"
            dangling_link = root / "dangling-link.md"
            dangling_link.symlink_to(dangling_target)
            with self.assertRaises(SystemExit):
                _call(
                    [
                        "bundle",
                        "render",
                        "--bundle",
                        str(paths["bundle"]),
                        "--output",
                        str(dangling_link),
                    ]
                )
            self.assertTrue(dangling_link.is_symlink())
            self.assertFalse(dangling_target.exists())


if __name__ == "__main__":
    unittest.main()
