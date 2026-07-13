from __future__ import annotations

import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from aet.evolution import (
    CandidateError,
    EvolutionTargetAdapter,
    TargetResolutionError,
    default_registry,
    infer_target_type,
    load_candidate,
    constitution_sha256,
)
from aet.evolution.constitution import CONSTITUTION


SHA_A = hashlib.sha256(b"baseline").hexdigest()
SHA_B = hashlib.sha256(b"candidate").hexdigest()


class ConstitutionTests(unittest.TestCase):
    def test_canonical_constitution_protects_evidence_and_evaluator(self) -> None:
        self.assertIn("unknown_is_not_pass", CONSTITUTION.immutable_semantics)
        self.assertIn("candidate_cannot_modify_evaluator", CONSTITUTION.immutable_semantics)
        self.assertIn("held_out_must_be_separate", CONSTITUTION.immutable_semantics)
        self.assertIn("src/aet/models.py::Status", CONSTITUTION.forbidden_targets)
        self.assertIn("src/aet/learn_statistics.py", CONSTITUTION.forbidden_targets)
        self.assertIn("src/aet/evolution/constitution.py", CONSTITUTION.forbidden_targets)
        self.assertFalse(CONSTITUTION.permits_target("src/aet/evolution/evaluators/audit_fixture.py"))
        self.assertFalse(CONSTITUTION.permits_target("/tmp/repo/src/aet/evolution/constitution.py"))
        self.assertFalse(CONSTITUTION.permits_target("/tmp/repo/tests/evolution/audit/held_out/suite.json"))
        self.assertIn("held_out/**", CONSTITUTION.forbidden_targets)


class RegistryTests(unittest.TestCase):
    def test_default_registry_has_every_bounded_target(self) -> None:
        self.assertEqual(
            {
                "skill": "supported",
                "audit-rule": "supported",
                "audit-profile": "supported",
                "review-policy": "supported",
                "trace-validator": "supported",
                "triage-policy": "supported",
            },
            {item.target_type: item.status for item in default_registry().list()},
        )

    def test_unknown_target_fails_closed(self) -> None:
        with self.assertRaises(TargetResolutionError):
            default_registry().get("arbitrary-code")

    def test_registered_targets_implement_full_adapter_protocol(self) -> None:
        for adapter in default_registry().list():
            self.assertIsInstance(adapter, EvolutionTargetAdapter)
            for method in ("inspect_target", "build_candidate", "validate_candidate", "replay", "adopt"):
                self.assertTrue(callable(getattr(adapter, method)))

    def test_registered_targets_inspect_real_assets_instead_of_placeholders(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for adapter in default_registry().list():
                path = root / ("SKILL.md" if adapter.target_type == "skill" else f"{adapter.target_type}.json")
                if adapter.target_type == "skill":
                    path.write_text("# Skill\n", encoding="utf-8")
                else:
                    path.write_text(json.dumps({"schema_version": f"{adapter.target_type}/v1"}), encoding="utf-8")
                inspected = adapter.inspect_target(path)
                self.assertEqual(inspected["target_type"], adapter.target_type)
                self.assertEqual(len(inspected["sha256"]), 64)

    def test_only_skill_is_safely_inferred(self) -> None:
        self.assertEqual("skill", infer_target_type(Path("skills/a/SKILL.md")))
        with self.assertRaises(TargetResolutionError):
            infer_target_type(Path("rules/context.yaml"))


class CandidateTests(unittest.TestCase):
    def test_v1_candidate_is_upgraded_in_memory_and_hash_bound(self) -> None:
        v1 = {
            "schema_version": "1.7.0",
            "report_kind": "learning_candidate",
            "candidate_id": "CAND-LEGACY",
            "target_file": "skills/a/SKILL.md",
            "baseline_sha256": SHA_A,
            "candidate_sha256": SHA_B,
            "operations": [{"type": "replace_editable_block", "id": "routing", "before_sha256": SHA_A, "new_text": "candidate"}],
            "edit_budget": {"max_operations": 3, "max_added_characters": 800, "max_deleted_characters": 400},
            "adoption": "human_required",
        }
        loaded = load_candidate(v1, candidate_content=b"candidate")
        self.assertEqual("evolution-candidate/v2", loaded.schema_version)
        self.assertEqual("skill", loaded.target.target_type)
        self.assertEqual("skills/a/SKILL.md", loaded.target.path)
        self.assertEqual(SHA_A, loaded.target.baseline_sha256)
        self.assertEqual(v1, loaded.source_document)

    def test_v2_directory_candidate_checks_candidate_artifact_hash(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            document = {
                "schema_version": "evolution-candidate/v2",
                "report_kind": "evolution_candidate",
                "candidate_id": "CAND-V2",
                "target": {"type": "audit-rule", "path": "rules/context.yaml", "baseline_sha256": SHA_A},
                "candidate_artifact": "candidate.yaml",
                "candidate_sha256": SHA_B,
                "source_patterns": ["PAT-1"],
                "operations": [{"op": "add", "path": "/rules/-", "value": "candidate"}],
                "budgets": {"max_operations": 3, "max_rules_added": 1, "max_severity_reductions": 0},
                "adoption": "human_required",
                "constitution_sha256": constitution_sha256(),
            }
            (root / "candidate.json").write_text(json.dumps(document), encoding="utf-8")
            (root / "candidate.yaml").write_bytes(b"candidate")
            self.assertEqual("audit-rule", load_candidate(root).target.target_type)
            (root / "candidate.yaml").write_bytes(b"tampered")
            with self.assertRaisesRegex(CandidateError, "hash"):
                load_candidate(root)

    def test_non_skill_v1_candidate_is_not_inferred(self) -> None:
        document = {
            "candidate_id": "CAND-UNSAFE",
            "target_file": "rules/context.yaml",
            "baseline_sha256": SHA_A,
            "candidate_sha256": SHA_B,
            "operations": [],
            "adoption": "human_required",
            "constitution_sha256": constitution_sha256(),
        }
        with self.assertRaises(TargetResolutionError):
            load_candidate(document, candidate_content=b"candidate")

    def test_v2_rejects_unknown_fields_and_unknown_target(self) -> None:
        document = {
            "schema_version": "evolution-candidate/v2",
            "report_kind": "evolution_candidate",
            "candidate_id": "CAND-BAD",
            "target": {"type": "unknown", "path": "x", "baseline_sha256": SHA_A},
            "candidate_sha256": SHA_B,
            "operations": [{"op": "replace", "path": "/x", "value": 1}],
            "budgets": {"max_operations": 3},
            "adoption": "human_required",
            "constitution_sha256": constitution_sha256(),
        }
        with self.assertRaises(TargetResolutionError):
            load_candidate(document, candidate_content=b"candidate")
        document["target"]["type"] = "audit-rule"
        document["surprise"] = True
        with self.assertRaisesRegex(CandidateError, "unknown field"):
            load_candidate(document, candidate_content=b"candidate")

    def test_v2_rejects_unbounded_operation_shape(self) -> None:
        document = {
            "schema_version": "evolution-candidate/v2",
            "report_kind": "evolution_candidate",
            "candidate_id": "CAND-OP",
            "target": {"type": "audit-rule", "path": "rules/context.yaml", "baseline_sha256": SHA_A},
            "candidate_sha256": SHA_B,
            "operations": [{"op": "execute", "path": "not-a-pointer", "value": "candidate", "shell": True}],
            "budgets": {"max_operations": 3},
            "adoption": "human_required",
            "constitution_sha256": constitution_sha256(),
        }
        with self.assertRaisesRegex(CandidateError, "operation"):
            load_candidate(document, candidate_content=b"candidate")


if __name__ == "__main__":
    unittest.main()
