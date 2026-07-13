"""Regression coverage for the evidence-gated learning preview."""

from __future__ import annotations

import json
import os
import hashlib
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aet.cli import main
from aet.discovery import discover_assets
from aet.learn import LearnError, gate, harvest, propose, replay_observed
from aet.rules import run_rules


class LearningPipelineTests(unittest.TestCase):
    def test_direct_report_harvest_enforces_evidence_only_privacy(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir()
            safe = evidence / "safe.json"
            safe.write_text(json.dumps({
                "report_kind": "audit", "runner": "codex",
                "findings": [{"rule_id": "SAFE_RULE", "status": "FAIL", "message": "password=discard-this-value"}],
            }), encoding="utf-8")
            result = harvest(runs=None, evidence=safe, output=root / "safe-out.json")
            self.assertNotIn("discard-this-value", json.dumps(result))

            for name, report in (
                ("runner", {"report_kind": "audit", "runner": "sk-" + "abcdefghijklmnop", "findings": []}),
                ("rule", {"report_kind": "audit", "findings": [{"rule_id": "password=supersecret", "status": "FAIL"}]}),
            ):
                source = evidence / f"{name}.json"
                source.write_text(json.dumps(report), encoding="utf-8")
                with self.subTest(name=name), self.assertRaisesRegex(LearnError, re.escape(str(source))):
                    harvest(runs=None, evidence=source, output=root / f"{name}-out.json")

    def test_harvest_globally_merges_duplicate_experience_status_order_independently(self) -> None:
        def row(status: str) -> dict[str, object]:
            deviations = [] if status == "PASS" else ["SHARED"]
            return {
                "experience_id": "EXP-SHARED", "source": {"sha256": "a" * 64, "report_kind": "audit", "path_redacted": True},
                "report_kind": "audit", "deviations": deviations,
                "phenomena": [{"code": "SHARED", "status": status}],
                "outcome": {"completed": not deviations, "workflow_deviation": deviations, "status": status},
                "privacy": {"raw_transcript_retained": False, "profile": "evidence-only"},
            }

        results = []
        for label, statuses in (("forward", ["PASS", "UNKNOWN", "FAIL"]), ("reverse", ["FAIL", "UNKNOWN", "PASS"])):
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                store = root / "store"
                store.mkdir()
                for index, status in enumerate(statuses):
                    (store / f"{index}.json").write_text(json.dumps({
                        "report_kind": "learning_experiences",
                        "privacy": {"profile": "evidence-only", "raw_transcript_retained": False},
                        "experiences": [row(status)],
                    }), encoding="utf-8")
                merged = harvest(runs=None, evidence=None, experience_store=store, output=root / "out.json")["experiences"]
                self.assertEqual(len(merged), 1)
                self.assertEqual(merged[0]["phenomena"], [{"code": "SHARED", "status": "FAIL"}])
                self.assertEqual(merged[0]["deviations"], ["SHARED"])
                self.assertEqual(merged[0]["outcome"]["status"], "FAIL")
                results.append(merged)
        self.assertEqual(results[0], results[1])

    def test_harvest_rejects_malformed_findings_with_source(self) -> None:
        for findings in (None, {}, ["not-an-object"]):
            with self.subTest(findings=findings), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                source = root / "report.json"
                source.write_text(json.dumps({"report_kind": "audit", "findings": findings}), encoding="utf-8")
                with self.assertRaisesRegex(LearnError, re.escape(str(source))):
                    harvest(runs=None, evidence=source, output=root / "out.json")

    def test_aet_run_parent_hash_is_read_once_for_multiple_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "run.json"
            source.write_text(json.dumps({
                "report_kind": "aet_run", "artifacts": {"audit": [
                    {"report": {"report_kind": "audit", "findings": []}},
                    {"report": {"report_kind": "audit", "findings": [{"rule_id": "X", "status": "UNKNOWN"}]}},
                ]},
            }), encoding="utf-8")
            original = Path.read_bytes
            reads = 0

            def counting(path: Path) -> bytes:
                nonlocal reads
                if path == source:
                    reads += 1
                return original(path)

            with mock.patch.object(Path, "read_bytes", counting):
                harvest(runs=None, evidence=source, output=root / "out.json")
            self.assertEqual(reads, 1)

    def test_harvest_normalizes_only_allowlisted_pack_and_run_children(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir()
            failed = {
                "schema_version": "1.8.0", "report_kind": "audit", "generated_at": "2026-07-13T01:00:00+00:00",
                "workspace_snapshot": {"digest": "repo-digest"},
                "findings": [{"rule_id": "AET-NESTED", "status": "FAIL"}],
            }
            (evidence / "pack.json").write_text(json.dumps({
                "report_kind": "evidence_pack", "generated_at": "2026-07-13T02:00:00+00:00",
                "components": {"audit": {"report": failed}, "duplicate": {"report": failed}, "pass": {"report": {
                    "report_kind": "review", "findings": [{"rule_id": "OK", "status": "PASS"}],
                }}},
                "arbitrary": {"report": {"report_kind": "audit", "findings": [{"rule_id": "MUST_NOT_RECURSE", "status": "FAIL"}]}},
            }), encoding="utf-8")
            (evidence / "run.json").write_text(json.dumps({
                "report_kind": "aet_run", "created_at": "2026-07-13T03:00:00+00:00",
                "repository": {"initial_workspace_snapshot": {"digest": "run-repo"}},
                "artifacts": {"evidence_pack": [{"report": {"report_kind": "evidence_pack", "components": {
                    "audit": {"report": {"report_kind": "audit", "findings": [{"rule_id": "RUN_UNKNOWN", "status": "UNKNOWN"}]}},
                }}}]},
            }), encoding="utf-8")
            output = root / "experiences.json"

            result = harvest(runs=None, evidence=evidence, output=output)

            rows = result["experiences"]
            self.assertEqual(sum("AET-NESTED" in row["deviations"] for row in rows), 1)
            self.assertEqual(sum("RUN_UNKNOWN" in row["deviations"] for row in rows), 1)
            self.assertFalse(any("MUST_NOT_RECURSE" in row["deviations"] for row in rows))
            nested = next(row for row in rows if "AET-NESTED" in row["deviations"])
            self.assertEqual(nested["source"]["component"], "audit")
            self.assertRegex(nested["source"]["parent_sha256"], r"^[0-9a-f]{64}$")
            passed = next(row for row in rows if row["report_kind"] == "review")
            self.assertEqual(passed["deviations"], [])

    def test_harvest_observed_replay_scores_keep_pair_context_and_deduplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir()
            score = {"status": "FAIL", "findings": [{"code": "BAD_TOOL_ARGUMENT", "status": "FAIL"}]}
            (evidence / "replay.json").write_text(json.dumps({
                "report_kind": "learning_observed_replay", "generated_at": "2026-07-13T04:00:00+00:00", "runner": "codex",
                "pairs": [{"task_id": "refund", "iteration": 2, "baseline": {**score, "fixture_sha256": "fixture-one"}, "candidate": {**score, "fixture_sha256": "fixture-one"}}],
            }), encoding="utf-8")
            (evidence / "score.json").write_text(json.dumps({
                "report_kind": "learning_observed_score", "observed_at": "2026-07-13T05:00:00+00:00",
                "task_id": "direct", "runner": "claude-code", "variant": "candidate", "iteration": 3,
                "fixture_sha256": "fixture-two", "status": "UNKNOWN",
                "findings": [{"code": "INFRASTRUCTURE_ERROR", "status": "UNKNOWN"}],
            }), encoding="utf-8")

            rows = harvest(runs=None, evidence=evidence, output=root / "out.json")["experiences"]

            paired = [row for row in rows if row["task"]["task_id"] == "refund"]
            self.assertEqual({row["target"]["variant"] for row in paired}, {"baseline", "candidate"})
            self.assertTrue(all(row["target"]["host"] == "codex" and row["task"]["iteration"] == 2 for row in paired))
            self.assertTrue(all(row["repository_fingerprint"] == "fixture-one" for row in paired))
            direct = next(row for row in rows if row["task"]["task_id"] == "direct")
            self.assertEqual((direct["target"]["host"], direct["target"]["variant"], direct["task"]["iteration"]), ("claude-code", "candidate", 3))
            self.assertEqual(direct["observed_at"], "2026-07-13T05:00:00+00:00")

    def test_harvest_preserves_missing_unknown_component_and_status_only_scores(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "pack.json").write_text(json.dumps({
                "report_kind": "evidence_pack", "components": {
                    "trace": {"status": "UNKNOWN", "reason": "trace was not supplied"},
                },
            }), encoding="utf-8")
            (evidence / "failed-score.json").write_text(json.dumps({
                "report_kind": "learning_observed_score", "status": "FAIL", "findings": [], "task_id": "failed",
            }), encoding="utf-8")
            (evidence / "unknown-score.json").write_text(json.dumps({
                "report_kind": "learning_observed_score", "status": "UNKNOWN", "findings": [], "task_id": "unknown",
            }), encoding="utf-8")

            rows = harvest(runs=None, evidence=evidence, output=root / "out.json")["experiences"]

            missing = next(row for row in rows if row["source"].get("component") == "trace")
            self.assertEqual(missing["outcome"]["status"], "UNKNOWN")
            self.assertFalse(missing["outcome"]["completed"])
            self.assertIn("EVIDENCE_COMPONENT_UNKNOWN", missing["deviations"])
            self.assertEqual(missing["phenomena"], [{"code": "EVIDENCE_COMPONENT_UNKNOWN", "status": "UNKNOWN"}])
            failed = next(row for row in rows if row["task"]["task_id"] == "failed")
            unknown = next(row for row in rows if row["task"]["task_id"] == "unknown")
            self.assertEqual(failed["deviations"], ["OBSERVED_SCORE_FAIL"])
            self.assertEqual(unknown["deviations"], ["OBSERVED_SCORE_UNKNOWN"])
            self.assertEqual((failed["outcome"]["completed"], unknown["outcome"]["completed"]), (False, False))
            self.assertEqual((failed["outcome"]["status"], unknown["outcome"]["status"]), ("FAIL", "UNKNOWN"))
            self.assertEqual(failed["phenomena"], [{"code": "OBSERVED_SCORE_FAIL", "status": "FAIL"}])
            self.assertEqual(unknown["phenomena"], [{"code": "OBSERVED_SCORE_UNKNOWN", "status": "UNKNOWN"}])

    def test_harvest_phenomena_cover_portable_trace_feedback_and_missing_fail_component(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir()
            trace = {
                "report_kind": "trace", "summary": {"UNKNOWN": 1},
                "trace": {"artifacts": [{"status": "UNKNOWN"}]},
            }
            (evidence / "trace.json").write_text(json.dumps(trace), encoding="utf-8")
            (evidence / "pack.json").write_text(json.dumps({
                "report_kind": "evidence_pack", "components": {
                    "trace": {"status": "UNKNOWN", "report": trace},
                    "review": {"status": "FAIL", "reason": "not supplied"},
                },
            }), encoding="utf-8")
            (evidence / "feedback.json").write_text(json.dumps({
                "report_kind": "audit_feedback", "adoption_grade": True, "recorded_at": "2026-07-13T07:00:00+00:00",
                "fixture_sha256": "fixture", "finding": "AET-X", "deviations": ["FALSE_NEGATIVE", "MISSING_RULE"],
            }), encoding="utf-8")

            rows = harvest(runs=None, evidence=evidence, output=root / "out.json")["experiences"]

            traces = [row for row in rows if row["report_kind"] == "trace"]
            self.assertEqual(len(traces), 2)
            for row in traces:
                self.assertEqual(set(row["deviations"]), {item["code"] for item in row["phenomena"]})
                self.assertIn({"code": "MISSING_TRACE_PROOF", "status": "UNKNOWN"}, row["phenomena"])
                self.assertIn({"code": "UNKNOWN_REQUIRES_PRESERVATION", "status": "UNKNOWN"}, row["phenomena"])
                self.assertEqual(row["outcome"]["status"], "UNKNOWN")
            feedback = next(row for row in rows if row["report_kind"] == "audit_feedback")
            self.assertEqual(set(feedback["deviations"]), {item["code"] for item in feedback["phenomena"]})
            self.assertTrue(all(item["status"] == "FAIL" for item in feedback["phenomena"]))
            missing_fail = next(row for row in rows if row["source"].get("component") == "review")
            self.assertEqual(missing_fail["deviations"], ["EVIDENCE_COMPONENT_FAIL"])
            self.assertEqual(missing_fail["phenomena"], [{"code": "EVIDENCE_COMPONENT_FAIL", "status": "FAIL"}])
            self.assertEqual(missing_fail["outcome"]["status"], "FAIL")
            self.assertFalse(missing_fail["outcome"]["completed"])

    def test_harvest_preserves_generic_report_and_component_wrapper_statuses(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "audit.json").write_text(json.dumps({"report_kind": "audit", "status": "FAIL", "findings": []}), encoding="utf-8")
            (evidence / "feedback.json").write_text(json.dumps({"report_kind": "audit_feedback", "status": "UNKNOWN", "adoption_grade": False}), encoding="utf-8")
            (evidence / "pack.json").write_text(json.dumps({
                "report_kind": "evidence_pack", "components": {
                    "audit": {"status": "UNKNOWN", "report": {"report_kind": "audit", "status": "PASS", "findings": []}},
                    "review": {"status": "FAIL", "report": {"report_kind": "review", "status": "PASS", "findings": []}},
                },
            }), encoding="utf-8")

            rows = harvest(runs=None, evidence=evidence, output=root / "out.json")["experiences"]

            audit = next(row for row in rows if row["report_kind"] == "audit" and "component" not in row["source"])
            feedback = next(row for row in rows if row["report_kind"] == "audit_feedback")
            wrapped_unknown = next(row for row in rows if row["source"].get("component") == "audit")
            wrapped_fail = next(row for row in rows if row["source"].get("component") == "review")
            self.assertIn({"code": "REPORT_STATUS_FAIL", "status": "FAIL"}, audit["phenomena"])
            self.assertIn({"code": "REPORT_STATUS_UNKNOWN", "status": "UNKNOWN"}, feedback["phenomena"])
            self.assertIn({"code": "EVIDENCE_COMPONENT_UNKNOWN", "status": "UNKNOWN"}, wrapped_unknown["phenomena"])
            self.assertIn({"code": "EVIDENCE_COMPONENT_FAIL", "status": "FAIL"}, wrapped_fail["phenomena"])
            for row in (audit, feedback, wrapped_unknown, wrapped_fail):
                self.assertFalse(row["outcome"]["completed"])
                self.assertEqual(set(row["deviations"]), {item["code"] for item in row["phenomena"]})

    def test_harvest_duplicate_children_merge_wrapper_severity_order_independently(self) -> None:
        report = {"report_kind": "audit", "status": "PASS", "findings": []}
        cases = {
            "pass_then_fail": [("passed", "PASS"), ("failed", "FAIL")],
            "fail_then_pass": [("failed", "FAIL"), ("passed", "PASS")],
            "unknown_then_fail": [("unknown", "UNKNOWN"), ("failed", "FAIL")],
            "fail_then_unknown": [("failed", "FAIL"), ("unknown", "UNKNOWN")],
        }
        for label, wrappers in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                evidence = root / "evidence"
                evidence.mkdir()
                components = {name: {"status": status, "report": report} for name, status in wrappers}
                (evidence / "pack.json").write_text(json.dumps({
                    "report_kind": "evidence_pack", "components": components,
                }), encoding="utf-8")

                rows = harvest(runs=None, evidence=evidence, output=root / "out.json")["experiences"]

                self.assertEqual(1, len(rows))
                self.assertEqual("failed", rows[0]["source"]["component"])
                self.assertIn({"code": "EVIDENCE_COMPONENT_FAIL", "status": "FAIL"}, rows[0]["phenomena"])
                self.assertNotIn({"code": "EVIDENCE_COMPONENT_UNKNOWN", "status": "UNKNOWN"}, rows[0]["phenomena"])
                self.assertEqual("FAIL", rows[0]["outcome"]["status"])

    def test_learning_feedback_and_legacy_store_upgrade_have_consistent_phenomena(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "feedback.json").write_text(json.dumps({
                "report_kind": "learning_feedback", "recorded_at": "2026-07-13T08:00:00+00:00",
                "run_sha256": "run", "reason_codes": ["Z_REASON", "A_REASON", "Z_REASON"],
            }), encoding="utf-8")
            feedback = harvest(runs=None, evidence=evidence, output=root / "feedback-out.json")["experiences"][0]
            self.assertEqual(feedback["deviations"], ["A_REASON", "Z_REASON"])
            self.assertEqual(feedback["phenomena"], [{"code": "A_REASON", "status": "FAIL"}, {"code": "Z_REASON", "status": "FAIL"}])

            legacy = {**feedback}
            legacy.pop("phenomena")
            legacy["deviations"] = ["OLD_B", "OLD_A", "OLD_B"]
            legacy["outcome"] = {"completed": False, "workflow_deviation": legacy["deviations"]}
            store = root / "store.json"
            store.write_text(json.dumps({
                "schema_version": "1.8.0", "report_kind": "learning_experiences", "generated_at": "now",
                "privacy": {"profile": "evidence-only", "raw_transcript_retained": False}, "experiences": [legacy],
            }), encoding="utf-8")
            upgraded = harvest(runs=None, evidence=None, experience_store=store, output=root / "upgraded.json")["experiences"][0]
            self.assertEqual(upgraded["deviations"], ["OLD_A", "OLD_B"])
            self.assertEqual(upgraded["phenomena"], [{"code": "OLD_A", "status": "UNKNOWN"}, {"code": "OLD_B", "status": "UNKNOWN"}])
            self.assertEqual(upgraded["outcome"]["status"], "UNKNOWN")

    def test_harvest_audit_feedback_uses_reproducible_context_and_keeps_legacy_id(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir()
            feedback = {
                "schema_version": "audit-feedback/v1", "report_kind": "audit_feedback",
                "recorded_at": "2026-07-13T06:00:00+00:00", "fixture_sha256": "fixture-feedback",
                "finding": "AET-CTX-003", "adoption_grade": True, "deviations": ["FALSE_NEGATIVE"],
            }
            feedback_path = evidence / "feedback.json"
            feedback_path.write_text(json.dumps(feedback), encoding="utf-8")
            legacy = {"report_kind": "audit", "findings": [{"rule_id": "OLD", "status": "FAIL"}]}
            legacy_path = evidence / "legacy.json"
            legacy_path.write_text(json.dumps(legacy), encoding="utf-8")

            rows = harvest(runs=None, evidence=evidence, output=root / "out.json")["experiences"]

            row = next(item for item in rows if item["report_kind"] == "audit_feedback")
            self.assertEqual(row["observed_at"], feedback["recorded_at"])
            self.assertEqual(row["repository_fingerprint"], "fixture-feedback")
            self.assertEqual(row["task"]["task_id"], "AET-CTX-003")
            old = next(item for item in rows if item["report_kind"] == "audit")
            self.assertEqual(old["experience_id"], f"EXP-{hashlib.sha256(legacy_path.read_bytes()).hexdigest()[:12]}")

    def test_experience_store_rejects_nested_private_or_secret_material(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            pack = {
                "schema_version": "1.8.0", "report_kind": "learning_experiences", "generated_at": "now",
                "privacy": {"profile": "evidence-only", "raw_transcript_retained": False},
                "experiences": [{
                    "experience_id": "EXP-X", "source": {"sha256": "a" * 64, "report_kind": "audit", "path_redacted": True},
                    "report_kind": "audit", "schema_version": "1", "observed_at": "now", "repository_fingerprint": "repo",
                    "workspace_snapshot": {"status": "UNKNOWN"}, "target": {"host": "UNKNOWN"},
                    "task": {"task_id": "x", "final_response": "token=secret"}, "outcome": {"completed": False},
                    "deviations": ["X"], "privacy": {"raw_transcript_retained": False, "profile": "evidence-only"},
                }],
            }
            source = root / "pack.json"
            source.write_text(json.dumps(pack), encoding="utf-8")
            with self.assertRaises(LearnError):
                harvest(runs=None, evidence=None, experience_store=source, output=root / "out.json")

    def test_experience_store_rejects_private_key_segments_without_false_positives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def pack(task: dict[str, object]) -> dict[str, object]:
                return {
                    "schema_version": "1.8.0", "report_kind": "learning_experiences", "generated_at": "now",
                    "privacy": {"profile": "evidence-only", "raw_transcript_retained": False},
                    "experiences": [{
                        "experience_id": "EXP-X", "source": {"sha256": "a" * 64, "report_kind": "audit", "path_redacted": True},
                        "report_kind": "audit", "schema_version": "1", "observed_at": "now", "repository_fingerprint": "repo",
                        "workspace_snapshot": {"status": "UNKNOWN"}, "target": {"host": "UNKNOWN"}, "task": task,
                        "outcome": {"completed": False}, "deviations": ["X"],
                        "privacy": {"raw_transcript_retained": False, "profile": "evidence-only"},
                    }],
                }

            for index, key in enumerate(("raw_response", "toolEvents", "environment_variables", "command-logs", "api_secret_value")):
                source = root / f"private-{index}.json"
                source.write_text(json.dumps(pack({"task_id": "x", "nested": {key: "private"}})), encoding="utf-8")
                with self.subTest(key=key), self.assertRaises(LearnError):
                    harvest(runs=None, evidence=None, experience_store=source, output=root / f"out-{index}.json")

            allowed = root / "allowed.json"
            allowed.write_text(json.dumps(pack({"task_id": "x", "response_time_ms": 2, "eventual_status": "FAIL", "catalog": "safe", "secretary_role": "reviewer"})), encoding="utf-8")
            result = harvest(runs=None, evidence=None, experience_store=allowed, output=root / "allowed-out.json")
            self.assertEqual(len(result["experiences"]), 1)

    def test_experience_store_rejects_credentials_in_keys_and_high_confidence_values(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def pack(detail: dict[str, object]) -> dict[str, object]:
                return {
                    "schema_version": "1.8.0", "report_kind": "learning_experiences", "generated_at": "now",
                    "privacy": {"profile": "evidence-only", "raw_transcript_retained": False},
                    "experiences": [{
                        "experience_id": "EXP-X", "source": {"sha256": "a" * 64, "report_kind": "audit", "path_redacted": True},
                        "report_kind": "audit", "schema_version": "1", "observed_at": "now", "repository_fingerprint": "repo",
                        "workspace_snapshot": {"status": "UNKNOWN"}, "target": {"host": "UNKNOWN"},
                        "task": {"task_id": "x", "detail": detail}, "outcome": {"completed": False}, "deviations": ["X"],
                        "privacy": {"raw_transcript_retained": False, "profile": "evidence-only"},
                    }],
                }

            private = (
                {"apiKey": "redacted"}, {"access-token": "redacted"}, {"authorization": "redacted"},
                {"nested": {"passwd": "redacted"}}, {"note": "sk-" + "1234567890abcdefghijkl"},
                {"note": "github_pat_1234567890abcdefghijkl"}, {"note": "Bearer abcdefghijklmnopqrstuvwxyz"},
                {"note": "password=hunter2-secret"},
            )
            for index, detail in enumerate(private):
                source = root / f"credential-{index}.json"
                source.write_text(json.dumps(pack(detail)), encoding="utf-8")
                with self.subTest(detail=detail), self.assertRaises(LearnError):
                    harvest(runs=None, evidence=None, experience_store=source, output=root / f"credential-out-{index}.json")

            allowed = root / "credential-allowed.json"
            allowed.write_text(json.dumps(pack({"token_count": 42, "secretary": "reviewer", "note": "sk-short"})), encoding="utf-8")
            result = harvest(runs=None, evidence=None, experience_store=allowed, output=root / "credential-allowed-out.json")
            self.assertEqual(len(result["experiences"]), 1)

    def test_experience_store_rejects_private_keys_and_provider_credentials_without_metadata_false_positives(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)

            def pack(detail: dict[str, object]) -> dict[str, object]:
                base = {
                    "experience_id": "EXP-X", "source": {"sha256": "a" * 64, "report_kind": "audit", "path_redacted": True},
                    "report_kind": "audit", "schema_version": "1", "observed_at": "now", "repository_fingerprint": "repo",
                    "workspace_snapshot": {"status": "UNKNOWN"}, "target": {"host": "UNKNOWN"}, "task": {"task_id": "x", "detail": detail},
                    "outcome": {"completed": False}, "deviations": ["X"], "privacy": {"raw_transcript_retained": False, "profile": "evidence-only"},
                }
                return {"schema_version": "1.8.0", "report_kind": "learning_experiences", "generated_at": "now", "privacy": {"profile": "evidence-only", "raw_transcript_retained": False}, "experiences": [base]}

            private = (
                {"privateKey": "redacted"}, {"note": "-----BEGIN PRIVATE KEY-----\nabc\n-----END PRIVATE KEY-----"},
                {"note": "AKIA" + "1234567890ABCDEF"}, {"note": "eyJhbGciOiJIUzI1NiJ9." + "eyJzdWIiOiIxMjM0NTY3ODkwIn0.abcdefghijklmnop"},
                {"note": "xoxb-" + "123456789012-123456789012-abcdefghijklmnopqrstuvwx"},
            )
            for index, detail in enumerate(private):
                source = root / f"provider-{index}.json"
                source.write_text(json.dumps(pack(detail)), encoding="utf-8")
                with self.subTest(detail=detail), self.assertRaises(LearnError):
                    harvest(runs=None, evidence=None, experience_store=source, output=root / f"provider-out-{index}.json")

            allowed = root / "provider-allowed.json"
            allowed.write_text(json.dumps(pack({"api_key_count": 2, "credential_count": 1, "authorization_status": "UNKNOWN", "token_count": 9})), encoding="utf-8")
            self.assertEqual(1, len(harvest(runs=None, evidence=None, experience_store=allowed, output=root / "provider-allowed-out.json")["experiences"]))

    def test_observed_scoring_json_records_ingestion_context(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            baseline = "<!-- aet-learn:immutable -->\nUNKNOWN.\n<!-- aet-learn:end -->\n<!-- aet-learn:editable id=\"x\" -->\nDo it.\n<!-- aet-learn:end -->\n"
            skill.write_text(baseline, encoding="utf-8")
            candidate = root / "candidate"
            candidate.mkdir()
            proposed = baseline.replace("Do it.", "Do it safely.")
            (candidate / "candidate.SKILL.md").write_text(proposed, encoding="utf-8")
            (candidate / "candidate.json").write_text(json.dumps({"candidate_id": "CAND-CONTEXT", "target_file": str(skill), "baseline_sha256": hashlib.sha256(baseline.encode()).hexdigest(), "candidate_sha256": hashlib.sha256(proposed.encode()).hexdigest(), "operations": [{"type": "replace_editable_block", "id": "x", "before_sha256": hashlib.sha256(b"Do it.\n").hexdigest(), "new_text": "Do it safely.\n"}]}), encoding="utf-8")
            fixture = root / "fixture" / "repo"
            fixture.mkdir(parents=True)
            suite = root / "suite"
            suite.mkdir()
            (suite / "task.json").write_text(json.dumps({
                "schema_version": "2.0", "task_id": "context-task", "prompt": "Report unknown.",
                "fixture": {"source": str(root / "fixture")}, "runner": {"allowed": ["scripted"]},
                "policy": {"network": "deny", "timeout_seconds": 10, "allowed_commands": []},
                "expected_behavior": {}, "script": {"events": [{"type": "final_response", "text": "UNKNOWN"}]},
            }), encoding="utf-8")

            replay = replay_observed(candidate=candidate, suite=[suite], output=root / "out", runner_name="scripted", rollouts=1)

            rollout = Path(replay["pairs"][0]["baseline"]["rollout"])
            score = json.loads((rollout / "scoring.json").read_text(encoding="utf-8"))
            self.assertEqual((score["task_id"], score["runner"], score["variant"], score["iteration"]), ("context-task", "scripted", "baseline", 0))
            self.assertRegex(score["fixture_sha256"], r"^[0-9a-f]{64}$")
            self.assertIsInstance(score["observed_at"], str)

    def test_experience_store_inspect_and_cross_project_mining_are_evidence_only(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            store = root / "experience-store"
            source_experiences = []
            for index, digest in enumerate(("repo-one", "repo-two"), start=1):
                evidence = root / f"project-{index}" / "evidence"
                evidence.mkdir(parents=True)
                (evidence / "audit.json").write_text(json.dumps({
                    "schema_version": "1.5.0", "report_kind": "audit",
                    "generated_at": f"2026-07-{index:02d}T00:00:00+00:00",
                    "workspace_snapshot": {"digest": digest},
                    "findings": [{"rule_id": "MISSING_TRACE_PROOF", "status": "FAIL"}],
                }), encoding="utf-8")
                experiences = root / f"experiences-{index}.json"
                self.assertEqual(main(["learn", "harvest", "--evidence", str(evidence), "--output", str(experiences)]), 0)
                self.assertEqual(main(["learn", "collect", "--experiences", str(experiences), "--store", str(store)]), 0)
                self.assertTrue(main(["learn", "collect", "--experiences", str(experiences), "--store", str(store)]) == 0)
                source_experiences.append(experiences)

            merged = root / "merged.json"
            inspected = root / "inspection.json"
            patterns = root / "patterns.json"
            self.assertEqual(main(["learn", "harvest", "--experience-store", str(store), "--output", str(merged)]), 0)
            self.assertEqual(main(["learn", "inspect", "--experiences", str(merged), "--output", str(inspected)]), 0)
            self.assertEqual(main(["learn", "mine", "--experiences", str(merged), "--output", str(patterns)]), 0)
            experience_data = json.loads(merged.read_text(encoding="utf-8"))
            self.assertEqual(len(experience_data["experiences"]), 2)
            self.assertTrue(all(row["privacy"]["raw_transcript_retained"] is False for row in experience_data["experiences"]))
            self.assertTrue(all(row["source"]["path_redacted"] is True for row in experience_data["experiences"]))
            malicious = root / "malicious.json"
            malicious_data = json.loads(merged.read_text(encoding="utf-8"))
            malicious_data["experiences"][0]["shell_output"] = "must not enter the store"
            malicious.write_text(json.dumps(malicious_data), encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["learn", "collect", "--experiences", str(malicious), "--store", str(store)])
            pattern = json.loads(patterns.read_text(encoding="utf-8"))["patterns"][0]
            self.assertEqual(pattern["support"]["repository_count"], 2)
            self.assertEqual(pattern["support"]["date_count"], 2)
            self.assertIn("MISSING_TRACE_PROOF", json.loads(inspected.read_text(encoding="utf-8"))["deviation_counts"])

    def test_gate_requires_disjoint_held_out_suite_and_enforces_complexity_budget(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            baseline = (
                "---\nname: demo\ndescription: Demo\n---\n\n"
                "<!-- aet-learn:immutable -->\nUNKNOWN is never a pass.\n<!-- aet-learn:end -->\n"
                "<!-- aet-learn:editable id=\"route\" -->\n" + ("Use the smallest safe workflow.\n" * 20) + "<!-- aet-learn:end -->\n"
            )
            skill.write_text(baseline, encoding="utf-8")
            candidate = root / "candidate"
            candidate.mkdir()
            proposed = baseline.replace("Use the smallest safe workflow.\n", "Use the smallest safe workflow and retain evidence.\n", 1)
            (candidate / "candidate.SKILL.md").write_text(proposed, encoding="utf-8")
            (candidate / "candidate.json").write_text(json.dumps({
                "candidate_id": "CAND-SEPARATION", "target_file": str(skill),
                "baseline_sha256": __import__("hashlib").sha256(baseline.encode()).hexdigest(),
                "candidate_sha256": __import__("hashlib").sha256(proposed.encode()).hexdigest(),
                "operations": [{"id": "route"}],
            }), encoding="utf-8")
            suite = root / "suite"
            suite.mkdir()
            (suite / "task.json").write_text(json.dumps({"task_id": "route", "required_patterns": ["retain evidence"]}), encoding="utf-8")
            result = gate(candidate=candidate, validation=suite, held_out=suite, output=root / "gate.json")
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("validation and held-out suites overlap", result["hard_gate_failures"])
            self.assertIn("skill_token_delta", result["metrics"]["cost"])

    def test_replay_isolates_candidate_renders_viewer_and_sleep_records_a_bounded_run(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: demo\ndescription: Demo\n---\n\n"
                "<!-- aet-learn:immutable -->\nUNKNOWN is never a pass.\n<!-- aet-learn:end -->\n"
                "<!-- aet-learn:editable id=\"route\" -->\nUse the smallest safe workflow.\n<!-- aet-learn:end -->\n",
                encoding="utf-8",
            )
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "trace.json").write_text(json.dumps({"report_kind": "trace", "summary": {"UNKNOWN": 1}, "trace": {"artifacts": [{"status": "UNKNOWN"}]}}), encoding="utf-8")
            validation, held_out = root / "validation", root / "held-out"
            validation.mkdir()
            held_out.mkdir()
            (validation / "trace.json").write_text(json.dumps({"task_id": "trace", "required_patterns": ["aet trace"]}), encoding="utf-8")
            (held_out / "unknown.json").write_text(json.dumps({"task_id": "unknown", "required_patterns": ["preserve UNKNOWN"]}), encoding="utf-8")
            output = root / "sleep"
            self.assertEqual(main([
                "learn", "sleep", "--evidence", str(evidence), "--target", str(skill), "--core", str(validation),
                "--validation", str(validation), "--held-out", str(held_out), "--output", str(output),
                "--max-candidates", "1", "--max-replays", "2", "--timeout-seconds", "30",
            ]), 0)
            run = json.loads((output / "learning-run.json").read_text(encoding="utf-8"))
            self.assertEqual(run["run_type"], "SKILL_EVOLUTION")
            self.assertEqual(run["state"], "STAGED")
            self.assertTrue(run["events"])
            gate_path = next((output / "gates").glob("*.json"))
            viewer = root / "viewer.html"
            self.assertEqual(main(["learn", "viewer", "--gate", str(gate_path), "--output", str(viewer)]), 0)
            self.assertIn("Evidence-Gated Evolution", viewer.read_text(encoding="utf-8"))

    def test_model_proposal_requires_bounded_unique_patch_ir_and_times_out(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "SKILL.md"
            skill.write_text(
                "---\nname: demo\ndescription: Demo\n---\n\n"
                "<!-- aet-learn:immutable -->\nUNKNOWN is never a pass.\n<!-- aet-learn:end -->\n"
                "<!-- aet-learn:editable id=\"route\" -->\nRoute safely.\n<!-- aet-learn:end -->\n",
                encoding="utf-8",
            )
            patterns = root / "patterns.json"
            patterns.write_text(json.dumps({"report_kind": "learning_patterns", "patterns": []}), encoding="utf-8")
            with self.assertRaises(LearnError):
                propose(
                    patterns=patterns, target=skill, output=root / "candidate", engine="model",
                    model_command=[__import__("sys").executable, "-c", "import time; time.sleep(1)"],
                    model_timeout_seconds=0.01, rejected=None,
                )

    def test_gate_binds_patch_ir_and_adoption_refuses_a_tampered_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            baseline = (
                "---\nname: demo\ndescription: Demo\n---\n\n"
                "<!-- aet-learn:immutable -->\nUNKNOWN is never a pass.\n<!-- aet-learn:end -->\n"
                "<!-- aet-learn:editable id=\"route\" -->\nVerify routes.\n<!-- aet-learn:end -->\n"
            )
            proposed = baseline.replace("Verify routes.", "Verify routes with `aet trace`.")
            skill.write_text(baseline, encoding="utf-8")
            candidate = root / "candidate"
            candidate.mkdir()
            candidate_id = "CAND-BOUND"
            (candidate / "candidate.SKILL.md").write_text(proposed, encoding="utf-8")
            (candidate / "candidate.json").write_text(json.dumps({
                "candidate_id": candidate_id, "target_file": str(skill),
                "baseline_sha256": __import__("hashlib").sha256(baseline.encode()).hexdigest(),
                "candidate_sha256": __import__("hashlib").sha256(proposed.encode()).hexdigest(),
                "operations": [{"type": "replace_editable_block", "id": "route", "before_sha256": __import__("hashlib").sha256("Verify routes.\n".encode()).hexdigest(), "new_text": "Verify routes with `aet trace`.\n"}],
            }), encoding="utf-8")
            gate = root / "gate.json"
            gate.write_text(json.dumps({
                "report_kind": "learning_gate", "candidate_id": candidate_id, "status": "PASS",
                "baseline_sha256": __import__("hashlib").sha256(baseline.encode()).hexdigest(),
                "candidate_sha256": __import__("hashlib").sha256(proposed.encode()).hexdigest(),
            }), encoding="utf-8")
            (candidate / "candidate.SKILL.md").write_text(proposed.replace("UNKNOWN is never a pass.", "UNKNOWN is a pass."), encoding="utf-8")
            previous = Path.cwd()
            try:
                os.chdir(root)
                with self.assertRaises(SystemExit):
                    main(["learn", "stage", "--candidate", str(candidate), "--gate", str(gate), "--output", str(root / "staged")])
                with self.assertRaises(SystemExit):
                    main(["learn", "adopt", "--yes", "--candidate", str(candidate), "--gate", str(gate)])
            finally:
                os.chdir(previous)
            self.assertEqual(skill.read_text(encoding="utf-8"), baseline)

    def test_gate_rejects_empty_or_unbound_patch_ir(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            baseline = "---\nname: demo\ndescription: Demo\n---\n\n<!-- aet-learn:immutable -->\nUNKNOWN is never a pass.\n<!-- aet-learn:end -->\n<!-- aet-learn:editable id=\"route\" -->\nVerify routes.\n<!-- aet-learn:end -->\n"
            proposed = baseline.replace("Verify routes.", "Verify routes with `aet trace`.")
            skill.write_text(baseline, encoding="utf-8")
            candidate = root / "candidate"
            candidate.mkdir()
            (candidate / "candidate.SKILL.md").write_text(proposed, encoding="utf-8")
            (candidate / "candidate.json").write_text(json.dumps({"candidate_id": "CAND-EMPTY", "target_file": str(skill), "baseline_sha256": __import__("hashlib").sha256(baseline.encode()).hexdigest(), "candidate_sha256": __import__("hashlib").sha256(proposed.encode()).hexdigest(), "operations": []}), encoding="utf-8")
            validation, held_out = root / "validation", root / "held-out"
            validation.mkdir()
            held_out.mkdir()
            (validation / "task.json").write_text(json.dumps({"task_id": "trace", "required_patterns": ["aet trace"]}), encoding="utf-8")
            (held_out / "task.json").write_text(json.dumps({"task_id": "held", "required_patterns": ["aet trace"]}), encoding="utf-8")
            result = gate(candidate=candidate, validation=validation, held_out=held_out, output=root / "gate.json")
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("candidate operations are not a valid bounded Patch IR", result["hard_gate_failures"])
    def test_rules_pipeline_replays_gates_stages_and_rejects_without_auto_adopting(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text(
                "---\nname: demo\ndescription: Demo skill\n---\n\n"
                "<!-- aet-learn:immutable -->\nUNKNOWN is never a pass.\n<!-- aet-learn:end -->\n\n"
                "<!-- aet-learn:editable id=\"routing-guidance\" -->\nUse the smallest safe workflow.\n<!-- aet-learn:end -->\n",
                encoding="utf-8",
            )
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "trace.json").write_text(json.dumps({
                "report_kind": "trace", "summary": {"PASS": 1, "FAIL": 0, "UNKNOWN": 1, "NOT_APPLICABLE": 0},
                "trace": {"execution": {"status": "PASS"}, "artifacts": [{"status": "UNKNOWN"}]},
            }), encoding="utf-8")
            experiences = root / "learn" / "experiences.json"
            patterns = root / "learn" / "patterns.json"
            candidate = root / "learn" / "candidates" / "CAND-0001"
            suite = root / "eval" / "validation"
            suite.mkdir(parents=True)
            task = {"task_id": "trace-proof", "required_patterns": ["aet trace"], "forbidden_patterns": ["UNKNOWN is a pass"]}
            (suite / "trace-proof.json").write_text(json.dumps(task), encoding="utf-8")
            held_out = root / "eval" / "held-out"
            held_out.mkdir(parents=True)
            (held_out / "unknown.json").write_text(json.dumps({**task, "task_id": "unknown-proof"}), encoding="utf-8")

            self.assertEqual(main(["learn", "harvest", "--evidence", str(evidence), "--output", str(experiences)]), 0)
            self.assertEqual(main(["learn", "mine", "--experiences", str(experiences), "--output", str(patterns)]), 0)
            self.assertEqual(main(["learn", "propose", "--engine", "rules", "--patterns", str(patterns), "--target", str(skill), "--output", str(candidate)]), 0)
            self.assertTrue((candidate / "candidate.SKILL.md").is_file())
            gate = root / "learn" / "gates" / "CAND-0001.json"
            self.assertEqual(main([
                "learn", "gate", "--candidate", str(candidate), "--validation", str(suite),
                "--held-out", str(held_out), "--output", str(gate),
            ]), 0)
            self.assertEqual(json.loads(gate.read_text(encoding="utf-8"))["status"], "PASS")
            self.assertEqual(main(["learn", "stage", "--candidate", str(candidate), "--gate", str(gate), "--output", str(root / "learn" / "staged")]), 0)
            self.assertEqual(main(["learn", "stage", "--candidate", str(candidate), "--gate", str(gate), "--output", str(root / "learn" / "staged")]), 0)
            self.assertIn("Use the smallest safe workflow.", skill.read_text(encoding="utf-8"))
            self.assertEqual(main(["learn", "reject", "--candidate", str(candidate), "--reason", "human declined", "--output", str(root / "learn" / "rejected")]), 0)

    def test_missing_hermes_skill_reports_a_migration_target_without_hiding_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stale = root / "skills" / "software-development" / "test-driven-development" / "SKILL.md"
            archive = root / "skills" / ".archive" / "curator-reconstructed" / "software-development" / "test-driven-development"
            archive.mkdir(parents=True)
            (archive / ".absorbed_into").write_text("software-delivery-workflow\n", encoding="utf-8")
            replacement = root / "skills" / "software-development" / "software-delivery-workflow" / "SKILL.md"
            replacement.parent.mkdir(parents=True)
            replacement.write_text("---\nname: software-delivery-workflow\ndescription: replacement\n---\n\nVerify it.\n", encoding="utf-8")
            instruction = root / "AGENTS.md"
            instruction.write_text(f"Read {stale} before work.\n", encoding="utf-8")

            findings = run_rules(root, discover_assets(root))
            missing = next(item for item in findings if item.rule_id == "AET-CTX-003")
            self.assertEqual(missing.status.value, "FAIL")
            self.assertIn("software-delivery-workflow", missing.remediation)

    def test_adopt_requires_explicit_confirmation_and_writes_a_decision_ledger(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            skill.write_text("---\nname: demo\ndescription: Demo\n---\n\n<!-- aet-learn:immutable -->\nUNKNOWN is never a pass.\n<!-- aet-learn:end -->\n<!-- aet-learn:editable id=\"route\" -->\nVerify routes.\n<!-- aet-learn:end -->\n", encoding="utf-8")
            baseline = skill.read_text(encoding="utf-8")
            candidate = root / ".aet" / "learn" / "candidate"
            candidate.mkdir(parents=True)
            proposed = skill.read_text(encoding="utf-8").replace("Verify routes.", "Verify routes with `aet trace`; attach the Trace path and preserve UNKNOWN when proof is missing.")
            candidate_id = "CAND-ADOPT"
            (candidate / "candidate.SKILL.md").write_text(proposed, encoding="utf-8")
            baseline_sha = __import__("hashlib").sha256(baseline.encode()).hexdigest()
            candidate_sha = __import__("hashlib").sha256(proposed.encode()).hexdigest()
            (candidate / "candidate.json").write_text(json.dumps({"candidate_id": candidate_id, "target_file": str(skill), "baseline_sha256": baseline_sha, "candidate_sha256": candidate_sha, "operations": [{"type": "replace_editable_block", "id": "route", "before_sha256": __import__("hashlib").sha256("Verify routes.\n".encode()).hexdigest(), "new_text": "Verify routes with `aet trace`; attach the Trace path and preserve UNKNOWN when proof is missing.\n"}]}), encoding="utf-8")
            gate = root / ".aet" / "learn" / "gate.json"
            gate.write_text(json.dumps({"report_kind": "learning_gate", "candidate_id": candidate_id, "status": "PASS", "baseline_sha256": baseline_sha, "candidate_sha256": candidate_sha}), encoding="utf-8")
            before = Path.cwd()
            try:
                os.chdir(root)
                with self.assertRaises(SystemExit):
                    main(["learn", "adopt", "--candidate", str(candidate), "--gate", str(gate)])
                self.assertEqual(main(["learn", "adopt", "--yes", "--candidate", str(candidate), "--gate", str(gate)]), 0)
            finally:
                os.chdir(before)
            self.assertEqual(skill.read_text(encoding="utf-8"), proposed)
            ledger = json.loads((root / ".aet" / "learn" / "decision-ledger.json").read_text(encoding="utf-8"))
            self.assertEqual(ledger["decisions"][0]["id"], "DEC-CAND-ADOPT")

    def test_gate_rejects_a_candidate_that_changes_outside_an_editable_block(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            skill = root / "skills" / "demo" / "SKILL.md"
            skill.parent.mkdir(parents=True)
            baseline = "---\nname: demo\ndescription: Demo\n---\n\n<!-- aet-learn:immutable -->\nUNKNOWN is never a pass.\n<!-- aet-learn:end -->\n<!-- aet-learn:editable id=\"route\" -->\nVerify routes.\n<!-- aet-learn:end -->\n"
            proposed = baseline.replace("description: Demo", "description: Tampered").replace("Verify routes.", "Verify routes with `aet trace`.")
            skill.write_text(baseline, encoding="utf-8")
            candidate = root / "candidate"
            candidate.mkdir()
            (candidate / "candidate.SKILL.md").write_text(proposed, encoding="utf-8")
            (candidate / "candidate.json").write_text(json.dumps({"candidate_id": "CAND-TAMPER", "target_file": str(skill), "baseline_sha256": __import__("hashlib").sha256(baseline.encode()).hexdigest(), "candidate_sha256": __import__("hashlib").sha256(proposed.encode()).hexdigest(), "operations": [{"id": "route"}]}), encoding="utf-8")
            suite = root / "suite"
            suite.mkdir()
            (suite / "task.json").write_text(json.dumps({"task_id": "trace", "required_patterns": ["aet trace"]}), encoding="utf-8")
            result = gate(candidate=candidate, validation=suite, held_out=suite, output=root / "gate.json")
            self.assertEqual(result["status"], "FAIL")
            self.assertIn("candidate changed outside editable blocks", result["hard_gate_failures"])


if __name__ == "__main__":
    unittest.main()
