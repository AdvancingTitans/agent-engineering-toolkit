"""Regression coverage for the evidence-gated learning preview."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from aet.cli import main
from aet.discovery import discover_assets
from aet.learn import gate
from aet.rules import run_rules


class LearningPipelineTests(unittest.TestCase):
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
            (held_out / "unknown.json").write_text(json.dumps(task), encoding="utf-8")

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
            candidate = root / ".aet" / "learn" / "candidate"
            candidate.mkdir(parents=True)
            proposed = skill.read_text(encoding="utf-8").replace("Verify routes.", "Verify routes with `aet trace`; attach the Trace path and preserve UNKNOWN when proof is missing.")
            candidate_id = "CAND-ADOPT"
            (candidate / "candidate.SKILL.md").write_text(proposed, encoding="utf-8")
            (candidate / "candidate.json").write_text(json.dumps({"candidate_id": candidate_id, "target_file": str(skill), "baseline_sha256": __import__("hashlib").sha256(skill.read_bytes()).hexdigest(), "candidate_sha256": __import__("hashlib").sha256(proposed.encode()).hexdigest(), "operations": []}), encoding="utf-8")
            gate = root / ".aet" / "learn" / "gate.json"
            gate.write_text(json.dumps({"report_kind": "learning_gate", "candidate_id": candidate_id, "status": "PASS"}), encoding="utf-8")
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
