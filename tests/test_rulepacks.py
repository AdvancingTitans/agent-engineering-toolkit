"""Contract tests for declarative, hash-bound audit rule packs."""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from aet.discovery import discover_assets
from aet.cli import main
from aet.rulepacks import RulePackError, load_rulepack, rulepack_metadata, shadow_diff
from aet.models import Evidence, Finding, Severity, Status
from aet.rules import run_rules


class RulePackTests(unittest.TestCase):
    def test_builtin_rulepack_preserves_existing_findings_and_has_stable_identity(self) -> None:
        root = Path(__file__).parent / "fixtures" / "broken_project"
        pack = load_rulepack()
        findings = run_rules(root, discover_assets(root), rulepack=pack)
        self.assertEqual(
            [(row.rule_id, row.status.value, row.severity.value) for row in findings],
            [
                ("AET-CTX-001", "FAIL", "ERROR"),
                ("AET-CTX-002", "FAIL", "ERROR"),
                ("AET-SKL-002", "FAIL", "ERROR"),
                ("AET-SKL-004", "UNKNOWN", "WARN"),
            ],
        )
        metadata = rulepack_metadata(pack)
        self.assertEqual(metadata["rulepack_id"], "builtin")
        self.assertEqual(len(metadata["rulepack_sha256"]), 64)
        self.assertEqual(metadata, rulepack_metadata(load_rulepack()))

    def test_rulepack_rejects_executable_or_unknown_detectors(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "malicious.json"
            path.write_text(json.dumps({
                "schema_version": "audit-rulepack/v1",
                "rulepack_id": "malicious",
                "revision": 1,
                "rules": [{
                    "rule_id": "AET-X-001",
                    "detector": {"type": "python", "module": "os"},
                    "result": {"status": "FAIL", "severity": "ERROR"},
                }],
            }), encoding="utf-8")
            with self.assertRaises(RulePackError):
                load_rulepack(path)
            malicious = json.loads(path.read_text(encoding="utf-8"))
            malicious["rules"][0]["detector"] = {"type": "json_script_target_exists", "files": ["../outside.json"]}
            path.write_text(json.dumps(malicious), encoding="utf-8")
            with self.assertRaises(RulePackError):
                load_rulepack(path)

    def test_shadow_preserves_unknown_instead_of_reporting_pass(self) -> None:
        unknown = Finding("AET-X", Status.UNKNOWN, Severity.WARN, "unknown", (Evidence("AGENTS.md"),), "verify")
        result = shadow_diff([unknown], [unknown], official_engine={}, candidate_engine={}, snapshot={})
        self.assertEqual(result["official_status"], "UNKNOWN")
        self.assertEqual(result["shadow_status"], "UNKNOWN")

    def test_declarative_package_script_rule_reproduces_a_real_missing_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "AGENTS.md").write_text("# Agent instructions\n", encoding="utf-8")
            (root / "package.json").write_text(json.dumps({"scripts": {"test": "node scripts/missing.js"}}), encoding="utf-8")
            pack = load_rulepack()
            pack["rules"].append({
                "rule_id": "AET-PKG-001",
                "revision": 1,
                "target_kinds": ["repository"],
                "detector": {"type": "json_script_target_exists", "files": ["package.json"]},
                "result": {
                    "status": "FAIL",
                    "severity": "ERROR",
                    "claim": "Package script points to a missing local target.",
                    "remediation": "Create the script target or correct package.json.",
                },
                "safety": {"core": False, "minimum_severity": "ERROR"},
            })
            findings = run_rules(root, discover_assets(root), rulepack=pack)
            match = [row for row in findings if row.rule_id == "AET-PKG-001"]
            self.assertEqual(len(match), 1)
            self.assertEqual(match[0].evidence[0].path, "package.json")
            self.assertEqual(match[0].status.value, "FAIL")

    def test_shadow_rulepack_never_changes_official_report_or_exit_code(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "AGENTS.md").write_text("# Agent instructions\n", encoding="utf-8")
            (root / "package.json").write_text(json.dumps({"scripts": {"test": "node scripts/missing.js"}}), encoding="utf-8")
            candidate = load_rulepack()
            candidate["rulepack_id"] = "candidate"
            candidate["rules"].append({
                "rule_id": "AET-PKG-001", "revision": 1, "target_kinds": ["repository"],
                "detector": {"type": "json_script_target_exists", "files": ["package.json"]},
                "result": {"status": "FAIL", "severity": "ERROR", "claim": "Missing package script target.", "remediation": "Fix the target."},
                "safety": {"core": False, "minimum_severity": "ERROR"},
            })
            candidate_path = root / "candidate-rulepack.json"
            candidate_path.write_text(json.dumps(candidate), encoding="utf-8")
            official, shadow = root / "audit.json", root / "shadow.json"
            exit_code = main([
                "audit", str(root), "--format", "json", "--output", str(official),
                "--shadow-rulepack", str(candidate_path), "--shadow-output", str(shadow),
            ])
            self.assertEqual(exit_code, 0)
            official_data = json.loads(official.read_text(encoding="utf-8"))
            shadow_data = json.loads(shadow.read_text(encoding="utf-8"))
            self.assertEqual(official_data["summary"]["FAIL"], 0)
            self.assertEqual(official_data["audit_engine"]["rulepack_id"], "builtin")
            self.assertEqual(shadow_data["official_status"], "PASS")
            self.assertEqual([row["rule_id"] for row in shadow_data["diff"]["added_findings"]], ["AET-PKG-001"])


if __name__ == "__main__":
    unittest.main()
