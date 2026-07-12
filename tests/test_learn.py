"""Regression coverage for the evidence-gated learning preview."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from aet.cli import main
from aet.discovery import discover_assets
from aet.learn import LearnError, gate, propose
from aet.rules import run_rules


class LearningPipelineTests(unittest.TestCase):
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
