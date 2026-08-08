from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aet.risk.errors import RiskPolicyError
from aet.risk.models import Factor
from aet.risk.policy import load_policy


ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "tests/fixtures/risk/risk-policy.json"


class RiskPolicyTests(unittest.TestCase):
    def test_loads_hash_bound_policy_and_classifies_surfaces(self) -> None:
        policy = load_policy(POLICY)
        self.assertEqual(policy.policy_id, "risk-golden-v1")
        self.assertEqual(len(policy.policy_sha256), 64)
        surface = policy.classify("apply_patch", {"path": "src/app.py"})
        self.assertTrue(surface.high_impact)
        self.assertEqual(surface.capability, "write")
        self.assertEqual(surface.asset_ids, ("source",))

    def test_monitor_surface_is_separate_from_capability(self) -> None:
        policy = load_policy(POLICY)
        surface = policy.classify("shell", {"target": ".aet/evidence/proof.json"})
        self.assertEqual(surface.capability, "execute")
        self.assertEqual(surface.monitoring_surface_ids, ("aet-evidence",))

    def test_policy_hash_is_canonical_across_formatting(self) -> None:
        original = json.loads(POLICY.read_text())
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            path.write_text(json.dumps(original, indent=4), encoding="utf-8")
            self.assertEqual(load_policy(POLICY).policy_sha256, load_policy(path).policy_sha256)

    def test_symlink_and_unknown_factor_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            link = root / "policy.json"
            link.symlink_to(POLICY)
            with self.assertRaises(RiskPolicyError):
                load_policy(link)
            raw = json.loads(POLICY.read_text())
            raw["not_applicable_factors"] = ["model_motive"]
            invalid = root / "invalid.json"
            invalid.write_text(json.dumps(raw), encoding="utf-8")
            with self.assertRaises(RiskPolicyError):
                load_policy(invalid)

    def test_not_applicable_factor_is_explicit(self) -> None:
        raw = json.loads(POLICY.read_text())
        raw["not_applicable_factors"] = [Factor.OVERSIGHT_RESISTANCE.value]
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "policy.json"
            path.write_text(json.dumps(raw), encoding="utf-8")
            self.assertEqual(load_policy(path).not_applicable_factors, (Factor.OVERSIGHT_RESISTANCE,))


if __name__ == "__main__":
    unittest.main()
