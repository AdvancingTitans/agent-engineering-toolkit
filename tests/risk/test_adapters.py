from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aet.risk.adapters import build_context, load_context
from aet.risk.errors import RiskInputError
from aet.risk.policy import load_policy
from aet.run_normalization import normalize_run


ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests/fixtures/risk"
MINIMAL_BUNDLE = ROOT / "tests/fixtures/evidence-bundles/minimal"


class RiskAdapterTests(unittest.TestCase):
    def test_native_codex_and_claude_runs_share_context_semantics(self) -> None:
        policy = load_policy(FIXTURES / "risk-policy.json")
        codex = load_context(FIXTURES / "codex-compound.jsonl", FIXTURES / "intent-v2.json", policy)
        claude = load_context(FIXTURES / "claude-equivalent.jsonl", FIXTURES / "intent-v2.json", policy)
        self.assertEqual(codex.context_key, claude.context_key)
        self.assertEqual(len(codex.records), len(claude.records))

    def test_normalized_directory_is_accepted(self) -> None:
        policy = load_policy(FIXTURES / "risk-policy.json")
        normalized = normalize_run("codex", FIXTURES / "codex-clean.jsonl", generation_id="generation-0")
        context = build_context(normalized, json.loads((FIXTURES / "intent-v2.json").read_text()), policy)
        self.assertEqual(context.run_group_id, "risk-clean")
        self.assertTrue(context.task_id.startswith("task-"))

    def test_cross_run_records_fail_closed(self) -> None:
        policy = load_policy(FIXTURES / "risk-policy.json")
        normalized = normalize_run("codex", FIXTURES / "codex-clean.jsonl", generation_id="generation-0")
        normalized["records"][0]["source_identity"]["run_group_id"] = "other"
        with self.assertRaises(RiskInputError):
            build_context(normalized, json.loads((FIXTURES / "intent-v2.json").read_text()), policy)

    def test_validated_bundle_directory_is_accepted_without_upgrading_run_facts(self) -> None:
        context = load_context(
            FIXTURES / "codex-clean.jsonl",
            FIXTURES / "intent-v2.json",
            load_policy(FIXTURES / "risk-policy.json"),
            bundle_path=MINIMAL_BUNDLE,
        )
        self.assertGreater(len(context.evidence), 0)
        self.assertEqual("risk-clean", context.run_group_id)

    def test_inferred_goal_cannot_be_authoritative_intent(self) -> None:
        raw = json.loads((FIXTURES / "intent-v2.json").read_text())
        raw["goal"]["source_type"] = "inferred"
        with tempfile.TemporaryDirectory() as temporary:
            intent = Path(temporary) / "intent.json"
            intent.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(RiskInputError):
                load_context(FIXTURES / "codex-clean.jsonl", intent, load_policy(FIXTURES / "risk-policy.json"))


if __name__ == "__main__":
    unittest.main()
