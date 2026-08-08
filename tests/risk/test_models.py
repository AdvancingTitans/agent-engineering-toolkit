from __future__ import annotations

import json
import unittest
from pathlib import Path

from aet.risk.models import (
    Coverage,
    EvidenceStrength,
    Factor,
    FactorFinding,
    RISK_DIAGNOSIS_SCHEMA,
    RiskDiagnosis,
    SourceRef,
    Status,
    to_primitive,
)
from aet.risk.schemas import SchemaKind, canonical_json, load_schema, validate_version
from aet.risk.errors import RiskInputError


ROOT = Path(__file__).resolve().parents[2]


class RiskModelsTests(unittest.TestCase):
    def test_status_and_factor_contract_is_exact(self) -> None:
        self.assertEqual(
            [item.value for item in Status],
            ["PASS", "FAIL", "UNKNOWN", "NOT_APPLICABLE"],
        )
        self.assertEqual(
            {item.value for item in Factor},
            {
                "goal_divergence_indicator",
                "harm_realization_capability",
                "oversight_resistance_indicator",
            },
        )

    def test_fail_requires_evidence_and_pass_requires_coverage(self) -> None:
        common = {
            "factor": Factor.GOAL_DIVERGENCE,
            "observable": "bounded behaviour",
            "strength": EvidenceStrength.DIRECT,
            "counter_evidence_refs": (),
            "limitations": (),
            "does_not_prove": ("stable internal motive",),
            "context_key": "r:g:t",
        }
        with self.assertRaisesRegex(ValueError, "FAIL requires"):
            FactorFinding(
                status=Status.FAIL,
                evidence_refs=(),
                coverage=Coverage(complete=True),
                **common,
            )
        with self.assertRaisesRegex(ValueError, "PASS requires"):
            FactorFinding(
                status=Status.PASS,
                evidence_refs=(),
                coverage=Coverage(complete=False, gaps=("missing result",)),
                **common,
            )

    def test_canonical_serialization_is_stable_and_has_no_score(self) -> None:
        finding = FactorFinding(
            factor=Factor.GOAL_DIVERGENCE,
            observable="No divergence in declared coverage.",
            status=Status.PASS,
            strength=EvidenceStrength.NONE,
            evidence_refs=(),
            counter_evidence_refs=(SourceRef("intent:user:1", source_type="intent"),),
            coverage=Coverage(complete=True, checked_surfaces=("src/",)),
            limitations=("bounded run only",),
            does_not_prove=("stable alignment",),
            context_key="run:generation:task",
        )
        diagnosis = RiskDiagnosis(
            schema_version=RISK_DIAGNOSIS_SCHEMA,
            evaluator_version="1.0.0",
            created_at="2026-08-01T00:00:00Z",
            policy_id="p",
            policy_sha256="a" * 64,
            findings=(finding,),
        )
        primitive = to_primitive(diagnosis)
        first = canonical_json(primitive)
        second = canonical_json(primitive)
        self.assertEqual(first, second)
        self.assertNotIn("score", first)
        self.assertEqual(json.loads(first)["findings"][0]["status"], "PASS")

    def test_schema_files_load_and_forbidden_fields_are_rejected(self) -> None:
        for kind in (SchemaKind.RISK_POLICY, SchemaKind.RISK_DIAGNOSIS):
            schema = load_schema(kind)
            self.assertEqual(schema["additionalProperties"], False)
        with self.assertRaises(RiskInputError):
            validate_version(
                SchemaKind.RISK_DIAGNOSIS,
                {"schema_version": RISK_DIAGNOSIS_SCHEMA, "overall_score": 0.9},
            )
        with self.assertRaises(RiskInputError):
            validate_version(
                SchemaKind.RISK_DIAGNOSIS,
                {"schema_version": RISK_DIAGNOSIS_SCHEMA},
            )

    def test_evaluation_suite_contract_and_fixture_paths_are_frozen(self) -> None:
        suite = json.loads((ROOT / "eval/behavioural-risk/suite.json").read_text())
        schema = json.loads((ROOT / "eval/behavioural-risk/suite-v1.schema.json").read_text())
        self.assertEqual(suite["schema_version"], "aet-risk-eval-suite/1.0")
        self.assertEqual(schema["additionalProperties"], False)
        self.assertGreaterEqual(len(suite["cases"]), 7)
        for case in suite["cases"]:
            self.assertTrue((ROOT / case["fixture"]).is_file(), case["fixture"])
            self.assertEqual(set(case["expected"]), {item.value for item in Factor})


if __name__ == "__main__":
    unittest.main()
