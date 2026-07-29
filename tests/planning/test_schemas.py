from __future__ import annotations

import json
import tempfile
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest import mock

from aet.planning.candidate_parser import parse_candidate
from aet.planning.errors import PlanningError
from aet.planning.schemas import (
    SchemaKind,
    load_schema,
    schema_path,
    validate_document,
)
from aet.planning.validator import validate_plan_candidate

from tests.planning.test_models import candidate_value
from tests.planning.test_validator import context_value


class PlanningSchemaTests(unittest.TestCase):
    def test_all_schema_kinds_and_runtime_documents_validate(self) -> None:
        context = context_value()
        candidate = candidate_value()
        result = validate_plan_candidate(
            context,
            parse_candidate(json.dumps(candidate)),
        )
        values = {
            SchemaKind.PLANNING_REQUEST: asdict(context.request),
            SchemaKind.PLANNING_CONTEXT: asdict(context),
            SchemaKind.PLAN_CANDIDATE: candidate,
            SchemaKind.EVIDENCE_LINKED_PLAN: result.plan,
            SchemaKind.PLAN_REFERENCE: {
                "schema_version": "plan-reference/1.0"
            },
            SchemaKind.PLAN_MANIFEST: {
                "schema_version": "plan-manifest/1.0"
            },
        }
        for kind, value in values.items():
            with self.subTest(kind=kind):
                self.assertTrue(schema_path(kind).is_file())
                self.assertEqual("object", load_schema(kind)["type"])
                validate_document(kind, value)

    def test_schema_version_shape_and_non_object_fail_closed(self) -> None:
        with self.assertRaises(PlanningError):
            schema_path(SchemaKind.PLANNING_REQUEST, "2.0")
        with self.assertRaises(PlanningError):
            validate_document(SchemaKind.PLANNING_REQUEST, [])
        for kind in (
            SchemaKind.EVIDENCE_LINKED_PLAN,
            SchemaKind.PLAN_REFERENCE,
            SchemaKind.PLAN_MANIFEST,
        ):
            with self.subTest(kind=kind):
                with self.assertRaises(PlanningError):
                    validate_document(kind, {"schema_version": "wrong/1.0"})
        with tempfile.TemporaryDirectory() as raw:
            path = Path(raw) / "schema.json"
            path.write_text("[]\n", encoding="utf-8")
            with mock.patch(
                "aet.planning.schemas.schema_path",
                return_value=path,
            ):
                with self.assertRaises(PlanningError):
                    load_schema(SchemaKind.PLANNING_REQUEST)


if __name__ == "__main__":
    unittest.main()
