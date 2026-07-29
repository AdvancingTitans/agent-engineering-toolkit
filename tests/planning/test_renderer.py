from __future__ import annotations

import unittest

from aet.planning.renderer import render_consumer_guide, render_plan_markdown
from aet.planning.validator import validate_plan_candidate

from tests.planning.test_models import candidate_value
from tests.planning.test_validator import context_value
from aet.planning.candidate_parser import parse_candidate
import json


class PlanningRendererTests(unittest.TestCase):
    def test_markdown_exposes_status_authority_references_and_limits(self) -> None:
        result = validate_plan_candidate(
            context_value(),
            parse_candidate(json.dumps(candidate_value())),
        )
        rendered = render_plan_markdown(result.plan)
        self.assertIn("Status: `READY_FOR_HUMAN_REVIEW`", rendered)
        self.assertIn("Authority: `PROPOSED`", rendered)
        self.assertIn("`EDIT-001`", rendered)
        self.assertIn("`ev-1`", rendered)
        self.assertIn("does not prove", rendered)
        self.assertEqual(rendered, render_plan_markdown(result.plan))
        guide = render_consumer_guide(result.plan)
        self.assertIn("plan.json", guide)
        self.assertIn("does not mean", guide)


if __name__ == "__main__":
    unittest.main()
