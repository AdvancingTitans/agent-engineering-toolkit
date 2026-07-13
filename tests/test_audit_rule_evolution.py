"""End-to-end evidence gate for a declarative audit-rule candidate."""

from __future__ import annotations

import json
import shutil
import tempfile
import unittest
from pathlib import Path

from aet.audit_evolution import (
    AuditEvolutionError,
    adopt_audit_rule,
    gate_audit_rule,
    propose_audit_rule,
    replay_audit_rule,
    stage_audit_rule,
)
from aet.rulepacks import load_rulepack


ROOT = Path(__file__).resolve().parents[1]


class AuditRuleEvolutionTests(unittest.TestCase):
    def test_real_false_negative_closes_through_replay_gate_stage_and_human_adopt(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary:
            root = Path(temporary)
            target = root / "rulepack.json"
            target.write_text(json.dumps(load_rulepack(), indent=2), encoding="utf-8")
            patterns = root / "patterns.json"
            patterns.write_text(json.dumps({"report_kind": "learning_patterns", "patterns": [{"pattern_id": "PAT-PKG", "kind": "MISSING_PACKAGE_SCRIPT", "evidence_refs": ["EXP-1"]}]}), encoding="utf-8")
            candidate = root / "candidate"
            metadata = propose_audit_rule(patterns=patterns, target=target, output=candidate)
            self.assertEqual(metadata["target"]["type"], "audit-rule")
            self.assertTrue((candidate / "candidate.rulepack.json").is_file())

            replay = replay_audit_rule(candidate=candidate, suite=ROOT / "tests/evolution/audit/validation/suite.json", output=root / "replay.json", project_root=ROOT)
            self.assertGreater(replay["candidate"]["passed"], replay["baseline"]["passed"])
            gate = gate_audit_rule(
                candidate=candidate,
                core=ROOT / "tests/evolution/audit/core/suite.json",
                validation=ROOT / "tests/evolution/audit/validation/suite.json",
                held_out=ROOT / "tests/evolution/audit/held_out/suite.json",
                adversarial=ROOT / "tests/evolution/audit/adversarial/suite.json",
                output=root / "gate.json", project_root=ROOT,
            )
            self.assertEqual(gate["status"], "PASS")
            staged = stage_audit_rule(candidate=candidate, gate=root / "gate.json", output=root / "staged")
            staged_candidate = Path(staged["path"])
            shadow = root / "shadow-aggregate.json"
            shadow.write_text(json.dumps({"report_kind": "audit_shadow_aggregate", "status": "PASS", "adoption_grade": True, "candidate_rulepack_sha256": metadata["candidate_sha256"], "run_count": 20, "repository_count": 5, "date_count": 3, "false_positive_count": 0, "unconfirmed_count": 0}), encoding="utf-8")
            with self.assertRaises(AuditEvolutionError):
                adopt_audit_rule(candidate=staged_candidate, gate=staged_candidate / "gate.json", shadow_aggregate=shadow, yes=False)
            adopted = adopt_audit_rule(candidate=staged_candidate, gate=staged_candidate / "gate.json", shadow_aggregate=shadow, yes=True)
            self.assertEqual(adopted["status"], "PASS")
            self.assertTrue(any(rule["rule_id"] == "AET-PKG-001" for rule in json.loads(target.read_text(encoding="utf-8"))["rules"]))

    def test_candidate_cannot_lower_or_delete_core_rule_semantics(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "rulepack.json"
            baseline = load_rulepack()
            target.write_text(json.dumps(baseline), encoding="utf-8")
            patterns = root / "patterns.json"
            patterns.write_text(json.dumps({"patterns": [{"pattern_id": "PAT-X", "kind": "MISSING_PACKAGE_SCRIPT"}]}), encoding="utf-8")
            candidate = root / "candidate"
            propose_audit_rule(patterns=patterns, target=target, output=candidate)
            proposed_path = candidate / "candidate.rulepack.json"
            proposed = json.loads(proposed_path.read_text(encoding="utf-8"))
            proposed["rules"] = [row for row in proposed["rules"] if row["rule_id"] != "AET-CTX-004"]
            proposed_path.write_text(json.dumps(proposed), encoding="utf-8")
            with self.assertRaises(AuditEvolutionError):
                replay_audit_rule(candidate=candidate, suite=ROOT / "tests/evolution/audit/core/suite.json", output=root / "replay.json", project_root=ROOT)

    def test_candidate_artifact_must_be_exactly_reconstructed_from_patch_ir(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "rulepack.json"
            target.write_text(json.dumps(load_rulepack()), encoding="utf-8")
            patterns = root / "patterns.json"
            patterns.write_text(json.dumps({"patterns": [{"pattern_id": "PAT-PKG", "kind": "MISSING_PACKAGE_SCRIPT"}]}), encoding="utf-8")
            candidate = root / "candidate"
            propose_audit_rule(patterns=patterns, target=target, output=candidate)
            artifact = candidate / "candidate.rulepack.json"
            value = json.loads(artifact.read_text(encoding="utf-8"))
            value["unexpected_policy"] = True
            artifact.write_text(json.dumps(value), encoding="utf-8")
            manifest = json.loads((candidate / "candidate.json").read_text(encoding="utf-8"))
            manifest["candidate_sha256"] = __import__("hashlib").sha256(artifact.read_bytes()).hexdigest()
            (candidate / "candidate.json").write_text(json.dumps(manifest), encoding="utf-8")
            with self.assertRaisesRegex(AuditEvolutionError, "Patch IR"):
                replay_audit_rule(candidate=candidate, suite=ROOT / "tests/evolution/audit/core/suite.json", output=root / "replay.json", project_root=ROOT)


if __name__ == "__main__":
    unittest.main()
