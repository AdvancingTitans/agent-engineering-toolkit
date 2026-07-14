"""Deterministic diagnosis and human-gated regression staging."""

from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest import mock

from aet.cli import main


class QualityLoopTests(unittest.TestCase):
    def _policy(self, root: Path, **mapping_updates: object) -> Path:
        mapping = {
            "candidate_repair_surface": "trace-validator",
            "owner": "verification-owner",
            "action": "require a fresh proof-bound Trace before a success claim",
            "confidence": "HIGH",
            "high_risk": False,
            "rule_conflict": False,
            "new_schema": False,
        }
        mapping.update(mapping_updates)
        path = root / "quality-policy.json"
        path.write_text(json.dumps({"schema_version": "quality-mapping/v1", "mappings": {"MISSING_TRACE_PROOF": mapping}}), encoding="utf-8")
        return path

    def _diagnosis(self, root: Path, *, policy_updates: dict[str, object] | None = None, **finding_updates: object) -> Path:
        finding = {
            "code": "MISSING_TRACE_PROOF",
            "status": "FAIL",
            "evidence_refs": ["events.jsonl", ".aet/evidence/trace.json"],
        }
        finding.update(finding_updates)
        report = root / "score.json"
        report.write_text(json.dumps({"schema_version": "1.8.0", "report_kind": "learning_observed_score", "findings": [finding]}), encoding="utf-8")
        output = root / "diagnosis.json"
        self.assertEqual(main(["quality", "diagnose", "--report", str(report), "--policy", str(self._policy(root, **(policy_updates or {}))), "--output", str(output)]), 0)
        return output

    def _experience_diagnosis(self, root: Path) -> Path:
        report = root / "experiences.json"
        report.write_text(json.dumps({
            "report_kind": "learning_experiences",
            "experiences": [{
                "experience_id": "EXP-1", "deviations": ["MISSING_TRACE_PROOF"],
                "phenomena": [{"code": "MISSING_TRACE_PROOF", "status": "UNKNOWN"}],
                "source": {"sha256": "a" * 64}, "observed_at": "2026-07-13T10:00:00+00:00",
            }],
        }), encoding="utf-8")
        output = root / "experience-diagnosis.json"
        self.assertEqual(main(["quality", "diagnose", "--report", str(report), "--policy", str(self._policy(root)), "--output", str(output)]), 0)
        return output

    def _pattern_diagnosis(self, root: Path) -> Path:
        report = root / "patterns.json"
        report.write_text(json.dumps({"report_kind": "learning_patterns", "patterns": [{"pattern_id": "PAT-1", "kind": "MISSING_TRACE_PROOF", "confidence": "HIGH", "evidence_refs": ["EXP-1"]}]}), encoding="utf-8")
        output = root / "pattern-diagnosis.json"
        self.assertEqual(main(["quality", "diagnose", "--report", str(report), "--policy", str(self._policy(root)), "--output", str(output)]), 0)
        return output

    def _badcase(self, root: Path, **updates: object) -> Path:
        fixture = root / "fixtures" / "proof" / "repo"
        fixture.mkdir(parents=True, exist_ok=True)
        (fixture / "README.md").write_text("proof fixture\n", encoding="utf-8")
        data = {
            "badcase_id": "BAD-001",
            "phenomenon_code": "MISSING_TRACE_PROOF",
            "status": "FAIL",
            "confirmed": True,
            "reproducible": True,
            "deidentified": True,
            "target_partition": "validation",
            "prompt": "Verify the declared proof and preserve UNKNOWN when it is absent.",
            "fixture": {"source": "fixtures/proof"},
            "policy": {"network": "deny", "timeout_seconds": 30},
            "expected_behavior": {"required_proof_ids": ["unit-tests"]},
            "evidence_refs": ["events.jsonl", ".aet/evidence/trace.json"],
            "observed_at": "2026-07-13T10:00:00+00:00",
        }
        data.update(updates)
        path = root / f"{data['badcase_id']}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def _promote(self, root: Path, badcase: Path, diagnosis: Path, output: Path | None = None) -> Path:
        output = output or root / "staging"
        self.assertEqual(main(["quality", "promote", "--badcase", str(badcase), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(output)]), 0)
        bundles = [path for path in output.iterdir() if path.is_dir()]
        self.assertEqual(len(bundles), 1)
        return bundles[0] / "task.json"

    def test_diagnosis_uses_versioned_mapping_and_preserves_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = self._diagnosis(root)
            data = json.loads(output.read_text(encoding="utf-8"))
            item = data["diagnoses"][0]
            self.assertEqual(data["mapping_version"], "quality-mapping/v1")
            self.assertRegex(data["mapping_sha256"], r"^[0-9a-f]{64}$")
            self.assertEqual(item["phenomenon_code"], "MISSING_TRACE_PROOF")
            self.assertEqual(item["status"], "FAIL")
            self.assertEqual(item["evidence_refs"], [".aet/evidence/trace.json", "events.jsonl"])
            self.assertEqual(item["candidate_repair_surface"], "trace-validator")
            self.assertEqual(item["owner"], "verification-owner")
            self.assertEqual(item["action"], "require a fresh proof-bound Trace before a success claim")
            self.assertEqual(item["confidence"], "HIGH")
            self.assertEqual(item["review_route"], {"required": False, "reasons": []})

    def test_review_routes_are_additive_and_never_change_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = self._diagnosis(root, status="UNKNOWN", confidence="LOW", policy_updates={"high_risk": True, "rule_conflict": True})
            item = json.loads(output.read_text(encoding="utf-8"))["diagnoses"][0]
            self.assertEqual(item["status"], "UNKNOWN")
            self.assertEqual(item["review_route"]["reasons"], ["HIGH_RISK", "LOW_CONFIDENCE", "RULE_CONFLICT"])

    def test_source_facts_cannot_weaken_policy_risk_or_confidence(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = self._diagnosis(root, confidence="HIGH", high_risk=False, policy_updates={"confidence": "LOW", "high_risk": True})
            item = json.loads(output.read_text(encoding="utf-8"))["diagnoses"][0]
            self.assertEqual("LOW", item["confidence"])
            self.assertEqual(["HIGH_RISK", "LOW_CONFIDENCE"], item["review_route"]["reasons"])

    def test_unknown_phenomenon_routes_new_schema_without_guessing_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = self._diagnosis(root, code="NEW_FAILURE_CODE")
            item = json.loads(output.read_text(encoding="utf-8"))["diagnoses"][0]
            self.assertIsNone(item["candidate_repair_surface"])
            self.assertIsNone(item["owner"])
            self.assertIsNone(item["action"])
            self.assertEqual(item["confidence"], "LOW")
            self.assertEqual(item["review_route"]["reasons"], ["LOW_CONFIDENCE"])

    def test_new_schema_route_requires_an_explicit_policy_fact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = self._diagnosis(root, policy_updates={"new_schema": True})
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["diagnoses"][0]["review_route"]["reasons"], ["NEW_SCHEMA"])

    def test_experience_and_pattern_inputs_are_supported(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.assertEqual(json.loads(self._experience_diagnosis(root).read_text(encoding="utf-8"))["diagnoses"][0]["phenomenon_code"], "MISSING_TRACE_PROOF")
            self.assertEqual(json.loads(self._pattern_diagnosis(root).read_text(encoding="utf-8"))["diagnoses"][0]["phenomenon_code"], "MISSING_TRACE_PROOF")

    def test_valid_badcase_stages_a_human_review_candidate_deterministically(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            first = self._promote(root, self._badcase(root), diagnosis, root / "first")
            second = self._promote(root, self._badcase(root), diagnosis, root / "second")
            left = json.loads(first.read_text(encoding="utf-8"))
            right = json.loads(second.read_text(encoding="utf-8"))
            quality = json.loads((first.parent / "quality.json").read_text(encoding="utf-8"))
            self.assertEqual(left, right)
            self.assertEqual(left["schema_version"], "2.0")
            self.assertTrue(left["task_id"].startswith("REG-"))
            self.assertTrue(left["prompt"])
            self.assertEqual(left["fixture"], {"source": "fixture"})
            self.assertEqual((first.parent / "fixture" / "repo" / "README.md").read_text(encoding="utf-8"), "proof fixture\n")
            self.assertEqual(left["policy"]["network"], "deny")
            self.assertEqual(left["expected_behavior"], {"required_proof_ids": ["unit-tests"]})
            self.assertEqual(quality["adoption"], "human_review_required")
            self.assertEqual(quality["target_partition"], "validation")
            self.assertEqual(len(quality["canonical_sha256"]), 64)
            self.assertEqual(quality["representative_evidence"], [".aet/evidence/trace.json", "events.jsonl"])
            self.assertEqual(quality["first_seen"], "2026-07-13T10:00:00Z")
            self.assertEqual(quality["last_seen"], "2026-07-13T10:00:00Z")
            self.assertEqual(quality["support"], 1)
            verification = root / "suite-verification.json"
            self.assertEqual(main(["learn", "suite", "verify", "--suite", str(first.parent), "--output", str(verification)]), 0)
            self.assertEqual(json.loads(verification.read_text(encoding="utf-8"))["status"], "PASS")

    def test_existing_same_candidate_is_updated_without_creating_a_duplicate(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            output = self._promote(root, self._badcase(root), diagnosis).parent.parent
            later = self._badcase(root, badcase_id="BAD-002", observed_at="2026-07-14T10:00:00+00:00")
            self._promote(root, later, diagnosis, output)
            quality = json.loads(next(output.glob("*/quality.json")).read_text(encoding="utf-8"))
            self.assertEqual(quality["support"], 2)
            self.assertEqual(quality["first_seen"], "2026-07-13T10:00:00Z")
            self.assertEqual(quality["last_seen"], "2026-07-14T10:00:00Z")
            self.assertEqual(quality["representative_evidence"], [".aet/evidence/trace.json", "events.jsonl"])

    def test_ambiguous_or_duplicate_badcase_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            for updates in ({"phenomenon_code": "NEW_FAILURE_CODE"}, {"duplicate_of": "BAD-000"}):
                with self.subTest(updates=updates), self.assertRaises(SystemExit):
                    main(["quality", "promote", "--badcase", str(self._badcase(root, **updates)), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(root / "candidate")])

    def test_unconfirmed_nonreproducible_or_identified_badcase_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            for updates in ({"confirmed": False}, {"reproducible": False}, {"deidentified": False}):
                with self.subTest(updates=updates), self.assertRaises(SystemExit):
                    main(["quality", "promote", "--badcase", str(self._badcase(root, **updates)), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(root / "candidate")])

    def test_missing_expected_behavior_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            with self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(self._badcase(root, expected_behavior={})), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(root / "candidate")])

    def test_missing_fixture_source_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            badcase = self._badcase(root, fixture={"source": "fixtures/missing"})
            with self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(badcase), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(root / "candidate")])

    def test_core_and_held_out_targets_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            for partition in ("staging", "core", "held-out", "held_out", "adversarial"):
                with self.subTest(partition=partition), self.assertRaises(SystemExit):
                    main(["quality", "promote", "--badcase", str(self._badcase(root, target_partition=partition)), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(root / "candidate")])

    def test_missing_or_malformed_policy_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "score.json"
            report.write_text(json.dumps({"report_kind": "learning_observed_score", "findings": [{"code": "MISSING_TRACE_PROOF", "status": "FAIL"}]}), encoding="utf-8")
            for policy in (root / "missing.json", root / "bad.json"):
                if policy.name == "bad.json":
                    policy.write_text(json.dumps({"schema_version": "quality-mapping/v1", "mappings": {"MISSING_TRACE_PROOF": {"owner": "guessed"}}}), encoding="utf-8")
                with self.subTest(policy=policy), self.assertRaises(SystemExit):
                    main(["quality", "diagnose", "--report", str(report), "--policy", str(policy), "--output", str(root / "out.json")])

    def test_schema_contract_and_formal_partition_paths(self) -> None:
        schema = Path(__file__).resolve().parents[1] / "schemas" / "quality-diagnosis-v1.schema.json"
        data = json.loads(schema.read_text(encoding="utf-8"))
        self.assertEqual(data["properties"]["schema_version"]["const"], "quality-diagnosis/v1")
        self.assertEqual(data["properties"]["report_kind"]["const"], "quality_diagnosis")
        self.assertEqual(data["properties"]["status_policy"]["const"], "Input status is preserved; diagnosis and review routing never rewrite it.")
        self.assertIn("mapping_sha256", data["required"])
        self.assertFalse(data["additionalProperties"])
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            for output in (root / "eval" / "candidate", root / "tests" / "evolution" / "candidate", root / "adversarial" / "candidate"):
                with self.subTest(output=output), self.assertRaises(SystemExit):
                    main(["quality", "promote", "--badcase", str(self._badcase(root, target_partition="validation")), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(output)])

    def test_policy_mismatch_and_tampered_diagnosis_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            badcase = self._badcase(root)
            policy = root / "quality-policy.json"
            changed = json.loads(policy.read_text(encoding="utf-8"))
            changed["mappings"]["MISSING_TRACE_PROOF"]["owner"] = "different-owner"
            policy.write_text(json.dumps(changed), encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(badcase), "--diagnosis", str(diagnosis), "--policy", str(policy), "--output", str(root / "staging")])
            self._policy(root)
            tampered = json.loads(diagnosis.read_text(encoding="utf-8"))
            tampered["diagnoses"][0]["owner"] = "guessed-owner"
            diagnosis.write_text(json.dumps(tampered), encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(badcase), "--diagnosis", str(diagnosis), "--policy", str(policy), "--output", str(root / "staging")])

    def test_tampered_confidence_or_review_route_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            badcase = self._badcase(root)
            for field, value in (
                ("confidence", "LOW"),
                ("review_route", {"required": True, "reasons": ["LOW_CONFIDENCE"]}),
            ):
                diagnosis = self._diagnosis(root)
                data = json.loads(diagnosis.read_text(encoding="utf-8"))
                data["diagnoses"][0][field] = value
                diagnosis.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(field=field), self.assertRaises(SystemExit):
                    main(["quality", "promote", "--badcase", str(badcase), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(root / field)])

    def test_promotion_rejects_tampered_diagnosis_schema_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            data = json.loads(diagnosis.read_text(encoding="utf-8"))
            data["schema_version"] = "quality-diagnosis/v2"
            diagnosis.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(self._badcase(root)), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(root / "staging")])

    def test_promotion_rejects_tampered_diagnosis_report_kind(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            data = json.loads(diagnosis.read_text(encoding="utf-8"))
            data["report_kind"] = "quality_summary"
            diagnosis.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(self._badcase(root)), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(root / "staging")])

    def test_promotion_rejects_tampered_diagnosis_evidence_refs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            data = json.loads(diagnosis.read_text(encoding="utf-8"))
            data["diagnoses"][0]["evidence_refs"] = ["tampered.json"]
            diagnosis.write_text(json.dumps(data), encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(self._badcase(root)), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(root / "staging")])

    def test_promotion_rejects_noncanonical_diagnosis_structure(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            badcase = self._badcase(root)
            for label, mutate in (
                ("missing_top_level", lambda data: data.pop("source_report_kind")),
                ("extra_item_field", lambda data: data["diagnoses"][0].update({"explanation": "untrusted"})),
            ):
                diagnosis = self._diagnosis(root)
                data = json.loads(diagnosis.read_text(encoding="utf-8"))
                mutate(data)
                diagnosis.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(label=label), self.assertRaises(SystemExit):
                    main(["quality", "promote", "--badcase", str(badcase), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(root / label)])

    def test_experience_phenomena_preserve_unknown_and_legacy_deviation_is_unknown(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            current = json.loads(self._experience_diagnosis(root).read_text(encoding="utf-8"))["diagnoses"][0]
            self.assertEqual(current["status"], "UNKNOWN")
            report = root / "legacy.json"
            report.write_text(json.dumps({"report_kind": "learning_experiences", "experiences": [{"experience_id": "EXP-OLD", "deviations": ["MISSING_TRACE_PROOF"], "source": {"sha256": "b" * 64}}]}), encoding="utf-8")
            output = root / "legacy-diagnosis.json"
            self.assertEqual(main(["quality", "diagnose", "--report", str(report), "--policy", str(self._policy(root)), "--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["diagnoses"][0]["status"], "UNKNOWN")

    def test_fixture_root_symbolic_link_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            badcase = self._badcase(root)
            real_fixture = root / "fixtures" / "proof"
            moved_fixture = root / "fixtures" / "real-proof"
            real_fixture.rename(moved_fixture)
            real_fixture.symlink_to(moved_fixture, target_is_directory=True)
            with self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(badcase), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(root / "staging")])

    def test_invalid_input_fails_closed_without_replacing_existing_output(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "invalid.json"
            report.write_text(json.dumps({"findings": [{"code": "MISSING_TRACE_PROOF", "status": "MAYBE"}]}), encoding="utf-8")
            output = root / "diagnosis.json"
            output.write_text("keep\n", encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["quality", "diagnose", "--report", str(report), "--policy", str(self._policy(root)), "--output", str(output)])
            self.assertEqual(output.read_text(encoding="utf-8"), "keep\n")

    def test_generated_task_is_formally_validated_before_any_bundle_write(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            output = root / "staging"
            with self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(self._badcase(root, policy={"network": "deny", "timeout_seconds": 30, "invented": True})), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(output)])
            self.assertFalse(output.exists())

    def test_empty_report_and_pattern_kinds_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name, report in (
                ("report", {"report_kind": "", "findings": [{"code": "MISSING_TRACE_PROOF", "status": "FAIL"}]}),
                ("pattern", {"report_kind": "learning_patterns", "patterns": [{"kind": "", "evidence_refs": ["x"]}]}),
            ):
                path = root / f"{name}.json"
                path.write_text(json.dumps(report), encoding="utf-8")
                with self.subTest(name=name), self.assertRaises(SystemExit):
                    main(["quality", "diagnose", "--report", str(path), "--policy", str(self._policy(root)), "--output", str(root / f"{name}-out.json")])

    def test_identity_includes_mapping_risk_decision_and_fixture_mode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "staging"
            normal = self._diagnosis(root)
            self._promote(root, self._badcase(root), normal, output)
            risky = self._diagnosis(root, policy_updates={"high_risk": True})
            self.assertEqual(main(["quality", "promote", "--badcase", str(self._badcase(root, badcase_id="BAD-002")), "--diagnosis", str(risky), "--policy", str(root / "quality-policy.json"), "--output", str(output)]), 0)
            self.assertEqual(len([path for path in output.iterdir() if path.is_dir()]), 2)

            mode_output = root / "mode-staging"
            fixture_file = root / "fixtures" / "proof" / "repo" / "README.md"
            fixture_file.chmod(0o644)
            self._promote(root, self._badcase(root, badcase_id="BAD-003"), normal, mode_output)
            fixture_file.chmod(0o755)
            self.assertEqual(main(["quality", "promote", "--badcase", str(self._badcase(root, badcase_id="BAD-004")), "--diagnosis", str(normal), "--policy", str(root / "quality-policy.json"), "--output", str(mode_output)]), 0)
            self.assertEqual(len([path for path in mode_output.iterdir() if path.is_dir()]), 2)

    def test_promotion_selects_diagnosis_by_code_and_status(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            data = json.loads(diagnosis.read_text(encoding="utf-8"))
            other = json.loads(json.dumps(data["diagnoses"][0]))
            other["status"] = "UNKNOWN"
            data["diagnoses"].append(other)
            data["diagnoses"].sort(key=lambda item: (item["phenomenon_code"], item["status"], item["evidence_refs"]))
            diagnosis.write_text(json.dumps(data), encoding="utf-8")
            self._promote(root, self._badcase(root), diagnosis)

    def test_destination_symlink_and_fixture_copy_races_are_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            output = root / "staging"
            task = self._promote(root, self._badcase(root), diagnosis, output)
            destination = task.parent
            shutil_target = root / "outside"
            shutil_target.mkdir()
            for child in destination.iterdir():
                if child.is_dir():
                    import shutil
                    shutil.rmtree(child)
                else:
                    child.unlink()
            destination.rmdir()
            destination.symlink_to(shutil_target, target_is_directory=True)
            with self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(self._badcase(root, badcase_id="BAD-002")), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(output)])
            self.assertEqual(list(shutil_target.iterdir()), [])

            race_root = Path(temporary) / "race"
            race_root.mkdir()
            race_diagnosis = self._diagnosis(race_root)
            badcase = self._badcase(race_root)
            fixture = race_root / "fixtures" / "proof"
            real = race_root / "fixtures" / "moved"
            from aet import quality as quality_module
            original_hash = quality_module._tree_sha256
            calls = 0
            def racing_hash(source: Path) -> str:
                nonlocal calls
                calls += 1
                if calls == 3:
                    fixture.rename(real)
                    fixture.symlink_to(real, target_is_directory=True)
                return original_hash(source)
            with mock.patch.object(quality_module, "_tree_sha256", side_effect=racing_hash), self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(badcase), "--diagnosis", str(race_diagnosis), "--policy", str(race_root / "quality-policy.json"), "--output", str(race_root / "staging")])

    def test_concurrent_promotion_preserves_support_and_complete_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            output = root / "staging"
            badcases = [self._badcase(root, badcase_id=f"BAD-{index:03d}") for index in range(1, 9)]
            def promote(path: Path) -> int:
                return main(["quality", "promote", "--badcase", str(path), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(output)])
            with ThreadPoolExecutor(max_workers=8) as executor:
                self.assertEqual(list(executor.map(promote, badcases)), [0] * 8)
            bundle = next(path for path in output.iterdir() if path.is_dir())
            quality = json.loads((bundle / "quality.json").read_text(encoding="utf-8"))
            task = json.loads((bundle / "task.json").read_text(encoding="utf-8"))
            self.assertEqual(quality["support"], 8)
            self.assertEqual(quality["support"], len(set(quality["source_badcase_ids"])))
            self.assertEqual(quality["confidence"], "HIGH")
            self.assertIn("mapping_sha256", quality)
            self.assertEqual(task["task_id"], f"REG-{quality['canonical_sha256'][:12].upper()}")
            sidecar_schema = json.loads((Path(__file__).resolve().parents[1] / "schemas" / "quality-regression-sidecar-v1.schema.json").read_text(encoding="utf-8"))
            self.assertFalse(sidecar_schema["additionalProperties"])
            self.assertEqual(sidecar_schema["properties"]["mapping_version"]["const"], "quality-mapping/v1")

    def test_malformed_existing_sidecar_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            output = root / "staging"
            task = self._promote(root, self._badcase(root), diagnosis, output)
            sidecar = task.parent / "quality.json"
            quality = json.loads(sidecar.read_text(encoding="utf-8"))
            quality["support"] = 99
            sidecar.write_text(json.dumps(quality), encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(self._badcase(root, badcase_id="BAD-002")), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(output)])

    def test_existing_task_identity_is_immutable_during_quality_update(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            output = root / "staging"
            task_path = self._promote(root, self._badcase(root), diagnosis, output)
            task = json.loads(task_path.read_text(encoding="utf-8"))
            task["prompt"] = "A different but still valid task."
            task_path.write_text(json.dumps(task), encoding="utf-8")
            with self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(self._badcase(root, badcase_id="BAD-002")), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(output)])
            self.assertEqual(json.loads(task_path.read_text(encoding="utf-8"))["prompt"], "A different but still valid task.")

    def test_update_interruption_before_sidecar_replace_preserves_old_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            output = root / "staging"
            task_path = self._promote(root, self._badcase(root), diagnosis, output)
            sidecar = task_path.parent / "quality.json"
            original_task = task_path.read_bytes()
            original_sidecar = sidecar.read_bytes()
            from aet import quality as quality_module
            original_rename = quality_module.os.rename
            def interrupt_sidecar(source: object, destination: object, **kwargs: object) -> None:
                if destination == "quality.json":
                    raise SystemExit("injected interruption before sidecar replace")
                original_rename(source, destination, **kwargs)
            with mock.patch.object(quality_module.os, "rename", side_effect=interrupt_sidecar), self.assertRaisesRegex(SystemExit, "injected interruption"):
                main(["quality", "promote", "--badcase", str(self._badcase(root, badcase_id="BAD-002")), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(output)])
            self.assertEqual(task_path.read_bytes(), original_task)
            self.assertEqual(sidecar.read_bytes(), original_sidecar)
            self.assertTrue((task_path.parent / "fixture").is_dir())
            self.assertFalse(any(path.name.startswith(".quality.json.") for path in task_path.parent.iterdir()))

    def test_concurrent_readers_never_observe_a_missing_or_partial_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            output = root / "staging"
            task_path = self._promote(root, self._badcase(root), diagnosis, output)
            destination = task_path.parent
            from aet import quality as quality_module
            original_replace = quality_module.os.replace
            observations: list[str] = []
            stop = threading.Event()
            def slow_directory_swap(source: object, target: object) -> None:
                original_replace(source, target)
                if Path(source) == destination:
                    time.sleep(0.05)
            def reader() -> None:
                while not stop.is_set():
                    try:
                        task = json.loads((destination / "task.json").read_text(encoding="utf-8"))
                        quality = json.loads((destination / "quality.json").read_text(encoding="utf-8"))
                        if not (destination / "fixture").is_dir() or task["task_id"] != f"REG-{quality['canonical_sha256'][:12].upper()}":
                            observations.append("partial")
                    except (OSError, KeyError, json.JSONDecodeError):
                        observations.append("missing")
            thread = threading.Thread(target=reader)
            thread.start()
            try:
                with mock.patch.object(quality_module.os, "replace", side_effect=slow_directory_swap):
                    self.assertEqual(main(["quality", "promote", "--badcase", str(self._badcase(root, badcase_id="BAD-002")), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(output)]), 0)
            finally:
                stop.set()
                thread.join()
            self.assertEqual(observations, [])

    def test_interrupted_first_publish_removes_unique_temporary_bundle(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            output = root / "staging"
            from aet import quality as quality_module
            original_replace = quality_module.os.replace
            def interrupt_publish(source: object, destination: object) -> None:
                target = Path(destination)
                if target.parent == output.resolve() and len(target.name) == 64:
                    raise SystemExit("injected first publish interruption")
                original_replace(source, destination)
            with mock.patch.object(quality_module.os, "replace", side_effect=interrupt_publish), self.assertRaisesRegex(SystemExit, "first publish interruption"):
                main(["quality", "promote", "--badcase", str(self._badcase(root)), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(output)])
            self.assertFalse(any(path.is_dir() and path.name.startswith(".") for path in output.iterdir()))

    def test_existing_bundle_swap_after_validation_fails_without_writing_outside(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            diagnosis = self._diagnosis(root)
            output = root / "staging"
            task_path = self._promote(root, self._badcase(root), diagnosis, output)
            destination = task_path.parent
            original_bundle = output / "original-bundle"
            outside = root / "outside"
            outside.mkdir()
            original_task = task_path.read_bytes()
            original_quality = (destination / "quality.json").read_bytes()
            from aet import quality as quality_module
            original_validate = quality_module._validate_candidate_bundle
            swapped = False
            def swap_after_validation(task: dict[str, object], quality: dict[str, object], digest: str) -> None:
                nonlocal swapped
                original_validate(task, quality, digest)
                if not swapped:
                    destination.rename(original_bundle)
                    destination.symlink_to(outside, target_is_directory=True)
                    swapped = True
            with mock.patch.object(quality_module, "_validate_candidate_bundle", side_effect=swap_after_validation), self.assertRaises(SystemExit):
                main(["quality", "promote", "--badcase", str(self._badcase(root, badcase_id="BAD-002")), "--diagnosis", str(diagnosis), "--policy", str(root / "quality-policy.json"), "--output", str(output)])
            self.assertTrue(swapped)
            self.assertEqual(list(outside.iterdir()), [])
            self.assertEqual((original_bundle / "task.json").read_bytes(), original_task)
            self.assertEqual((original_bundle / "quality.json").read_bytes(), original_quality)


if __name__ == "__main__":
    unittest.main()
