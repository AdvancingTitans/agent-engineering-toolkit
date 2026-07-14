"""Safety contracts for bounded audit and evidence policy targets."""

from __future__ import annotations

import tempfile
import unittest
import json
import os
import subprocess
import sys
from pathlib import Path

from aet.policy_targets import PolicyTargetError, apply_audit_profile, evaluate_trace_validator, gate_policy_candidate, propose_policy_candidate, validate_policy_transition
from aet.models import Evidence, Finding, Severity, Status
from aet.cli import main


class PolicyTargetTests(unittest.TestCase):
    def test_audit_profile_can_tighten_but_not_disable_or_globally_exclude(self) -> None:
        baseline = {"schema_version": "audit-profile/v1", "rules": {"AET-SKL-004": {"enabled": True, "severity": "WARN"}}, "path_policy": {"sensitive": []}, "exclusions": []}
        candidate = {"schema_version": "audit-profile/v1", "rules": {"AET-SKL-004": {"enabled": True, "severity": "ERROR"}}, "path_policy": {"sensitive": ["src/auth/**"]}, "exclusions": []}
        validate_policy_transition("audit-profile", baseline, candidate)
        candidate["rules"]["AET-SKL-004"]["enabled"] = False
        with self.assertRaises(PolicyTargetError):
            validate_policy_transition("audit-profile", baseline, candidate)
        candidate["rules"]["AET-SKL-004"]["enabled"] = True
        candidate["exclusions"] = [{"pattern": "**", "reason": "silence all"}]
        with self.assertRaises(PolicyTargetError):
            validate_policy_transition("audit-profile", baseline, candidate)

    def test_audit_profile_applies_sensitive_paths_and_only_preapproved_exclusions(self) -> None:
        baseline = {
            "schema_version": "audit-profile/v1", "rules": {},
            "path_policy": {"sensitive": ["src/auth/**"]},
            "exclusions": [{"pattern": "vendor/**", "reason": "approved generated dependency"}],
        }
        findings = [
            Finding("AET-X", Status.UNKNOWN, Severity.WARN, "sensitive", (Evidence("src/auth/login.py"),), "fix", "1"),
            Finding("AET-Y", Status.FAIL, Severity.ERROR, "vendor", (Evidence("vendor/lib.md"),), "fix", "1"),
        ]
        applied = apply_audit_profile(findings, baseline)
        self.assertEqual([row.rule_id for row in applied], ["AET-X"])
        self.assertEqual(applied[0].severity, Severity.ERROR)
        candidate = json.loads(json.dumps(baseline))
        candidate["exclusions"].append({"pattern": "docs/examples/**", "reason": "new suppression"})
        with self.assertRaises(PolicyTargetError):
            validate_policy_transition("audit-profile", baseline, candidate)
    def test_review_policy_may_add_proof_and_sensitive_paths_but_not_remove_them(self) -> None:
        baseline = {"schema_version": "review-policy/v1", "changed_path_budget": 10, "path_classes": {"sensitive": ["src/auth/**"]}, "proof_requirements": {"sensitive": ["unit-tests"]}}
        candidate = {"schema_version": "review-policy/v1", "changed_path_budget": 8, "path_classes": {"sensitive": ["src/auth/**", ".github/workflows/**"]}, "proof_requirements": {"sensitive": ["unit-tests", "security-scan"]}}
        validate_policy_transition("review-policy", baseline, candidate)
        candidate["proof_requirements"]["sensitive"] = []
        with self.assertRaises(PolicyTargetError):
            validate_policy_transition("review-policy", baseline, candidate)

    def test_trace_validator_uses_safe_junit_dsl_and_never_shell(self) -> None:
        baseline = {"schema_version": "trace-validator/v1", "validator": "junit", "requirements": {"failures_max": 0, "errors_max": 0, "tests_min": 2, "skipped_max": 1}}
        candidate = {**baseline, "requirements": {**baseline["requirements"], "skipped_max": 0}}
        validate_policy_transition("trace-validator", baseline, candidate)
        with tempfile.TemporaryDirectory() as temporary:
            report = Path(temporary) / "junit.xml"
            report.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0"/>', encoding="utf-8")
            self.assertEqual(evaluate_trace_validator(candidate, report)["status"], "PASS")
            report.write_text('<testsuite tests="2" failures="0" errors="0" skipped="1"/>', encoding="utf-8")
            self.assertEqual(evaluate_trace_validator(candidate, report)["status"], "FAIL")
        malicious = {**candidate, "command": "python validator.py"}
        with self.assertRaises(PolicyTargetError):
            validate_policy_transition("trace-validator", baseline, malicious)

    def test_trace_validator_rejects_an_unchanged_preexisting_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "junit.xml"
            report.write_text('<testsuite tests="2" failures="0" errors="0" skipped="0"/>', encoding="utf-8")
            policy = root / "validator.json"
            policy.write_text(json.dumps({"schema_version": "trace-validator/v1", "validator": "junit", "requirements": {"failures_max": 0, "errors_max": 0, "tests_min": 2}}), encoding="utf-8")
            previous = Path.cwd()
            try:
                os.chdir(root)
                with self.assertRaises(SystemExit):
                    main(["trace", "--artifact", "junit.xml", "--validator-policy", "validator.json", "--validate-artifact", "junit.xml", "--output", "trace.json", "--", sys.executable, "-c", "pass"])
            finally:
                os.chdir(previous)

    def test_failed_trace_validator_blocks_reuse_and_is_visible_in_summary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(["git", "init"], cwd=root, check=True, capture_output=True)
            subprocess.run(["git", "config", "user.email", "aet@example.test"], cwd=root, check=True)
            subprocess.run(["git", "config", "user.name", "AET test"], cwd=root, check=True)
            (root / ".gitignore").write_text(".aet/\n", encoding="utf-8")
            (root / "README.md").write_text("base\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=root, check=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=root, check=True, capture_output=True)
            policy = root / "validator.json"
            policy.write_text(json.dumps({"schema_version": "trace-validator/v1", "validator": "junit", "requirements": {"failures_max": 0, "errors_max": 0, "tests_min": 2}}), encoding="utf-8")
            output = root / ".aet" / "trace.json"
            command = [sys.executable, "-c", "from pathlib import Path; Path('junit.xml').write_text('<testsuite tests=\"1\" failures=\"1\" errors=\"0\"/>')"]
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["trace", "--artifact", "junit.xml", "--validator-policy", "validator.json", "--validate-artifact", "junit.xml", "--output", str(output), "--", *command]), 1)
                report = json.loads(output.read_text(encoding="utf-8"))
                self.assertEqual(report["summary"]["FAIL"], 1)
                with self.assertRaises(SystemExit):
                    main(["trace", "--reuse-if-fresh", "--artifact", "junit.xml", "--output", str(output), "--", *command])
            finally:
                os.chdir(previous)

    def test_triage_policy_can_rank_but_cannot_hide_or_rewrite_findings(self) -> None:
        baseline = {"schema_version": "triage-policy/v1", "weights": {"severity": 40}, "critical_paths": []}
        candidate = {"schema_version": "triage-policy/v1", "weights": {"severity": 40, "critical_path": 20}, "critical_paths": ["src/auth/**"]}
        validate_policy_transition("triage-policy", baseline, candidate)
        candidate["hide_findings"] = True
        with self.assertRaises(PolicyTargetError):
            validate_policy_transition("triage-policy", baseline, candidate)

    def test_review_policy_candidate_improves_separate_validation_and_held_out_cases(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            target = root / "review-policy.json"
            target.write_text(json.dumps({
                "schema_version": "review-policy/v1", "changed_path_budget": 10,
                "path_classes": {"sensitive": ["src/auth/**"]},
                "proof_requirements": {"sensitive": ["unit-tests"]},
            }), encoding="utf-8")
            proposal = root / "proposal.json"
            proposal.write_text(json.dumps({"operations": [
                {"op": "replace", "path": "/changed_path_budget", "value": 8},
                {"op": "replace", "path": "/path_classes/sensitive", "value": ["src/auth/**", ".github/workflows/**"]},
                {"op": "replace", "path": "/proof_requirements/sensitive", "value": ["unit-tests", "security-scan"]}
            ]}), encoding="utf-8")
            candidate = root / "candidate"
            propose_policy_candidate(target_type="review-policy", target=target, proposal=proposal, output=candidate)
            validation = root / "validation.json"
            held_out = root / "held-out.json"
            core = root / "core.json"
            adversarial = root / "adversarial.json"
            validation.write_text(json.dumps({"schema_version": "policy-task/v1", "suite_id": "review-validation", "tasks": [{"task_id": "REV-V-1", "input": {"changed_paths": ["src/auth/login.py"], "provided_proofs": ["unit-tests"]}, "expected": {"compliant": False, "missing_proofs": ["security-scan"]}}]}), encoding="utf-8")
            held_out.write_text(json.dumps({"schema_version": "policy-task/v1", "suite_id": "review-held-out", "tasks": [{"task_id": "REV-H-1", "input": {"changed_paths": [".github/workflows/release.yml"], "provided_proofs": ["unit-tests"]}, "expected": {"compliant": False, "missing_proofs": ["security-scan"]}}]}), encoding="utf-8")
            core.write_text(json.dumps({"schema_version": "policy-task/v1", "suite_id": "review-core", "tasks": [{"task_id": "REV-C-1", "input": {"changed_paths": ["README.md"], "provided_proofs": []}, "expected": {"compliant": True, "missing_proofs": []}}]}), encoding="utf-8")
            adversarial.write_text(json.dumps({"schema_version": "policy-task/v1", "suite_id": "review-adversarial", "tasks": [{"task_id": "REV-A-1", "input": {"changed_paths": ["src/auth/token.py"], "provided_proofs": ["unit-tests"]}, "expected": {"compliant": False, "missing_proofs": ["security-scan"]}}]}), encoding="utf-8")
            gate = gate_policy_candidate(candidate=candidate, core=core, validation=validation, held_out=held_out, adversarial=adversarial, output=root / "gate.json", project_root=root)
            self.assertEqual(gate["status"], "PASS")
            self.assertGreater(gate["metrics"]["validation"]["candidate"]["passed"], gate["metrics"]["validation"]["baseline"]["passed"])


if __name__ == "__main__":
    unittest.main()
