"""Regression tests for isolated observed runner evidence and deterministic scores."""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
import unittest
from pathlib import Path

from aet.learn import replay_observed


class ObservedLearningTests(unittest.TestCase):
    def _candidate(self, root: Path) -> Path:
        skill = root / "skills" / "demo" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        baseline = "<!-- aet-learn:immutable -->\nUNKNOWN is never a pass.\n<!-- aet-learn:end -->\n<!-- aet-learn:editable id=\"route\" -->\nTrace required.\n<!-- aet-learn:end -->\n"
        skill.write_text(baseline, encoding="utf-8")
        candidate = root / "candidate"
        candidate.mkdir()
        proposed = baseline.replace("Trace required.", "Trace required; attach evidence.")
        (candidate / "candidate.SKILL.md").write_text(proposed, encoding="utf-8")
        (candidate / "candidate.json").write_text(json.dumps({"candidate_id": "CAND-OBSERVED", "target_file": str(skill), "baseline_sha256": hashlib.sha256(baseline.encode()).hexdigest(), "candidate_sha256": hashlib.sha256(proposed.encode()).hexdigest(), "operations": [{"type": "replace_editable_block", "id": "route", "before_sha256": hashlib.sha256(b"Trace required.\n").hexdigest(), "new_text": "Trace required; attach evidence.\n"}]}), encoding="utf-8")
        return candidate

    def _task(self, root: Path, *, with_trace: bool) -> Path:
        fixture = root / "fixture" / "repo"
        (fixture / "bin").mkdir(parents=True)
        runner = fixture / "bin" / "aet"
        runner.write_text("#!/bin/sh\nmkdir -p .aet/evidence\nprintf '{}' > .aet/evidence/trace.json\n", encoding="utf-8")
        runner.chmod(0o755)
        suite = root / "suite"
        suite.mkdir()
        script = [{"type": "command", "argv": ["bin/aet", "trace", "--proof", "unit-tests", "--output", ".aet/evidence/trace.json", "--", "true"]}] if with_trace else []
        script.append({"type": "final_response", "text": "Tests passed. Evidence: .aet/evidence/trace.json"})
        task = {"schema_version": "2.0", "task_id": "TRACE-PROOF-001", "prompt": "Confirm unit tests with evidence.", "fixture": {"source": str(root / "fixture")}, "runner": {"allowed": ["scripted"]}, "policy": {"network": "deny", "timeout_seconds": 10, "max_commands": 3, "allowed_write_paths": [".aet/**"], "forbidden_write_paths": ["src/**", "tests/**"], "allowed_commands": ["bin/aet trace"]}, "expected_behavior": {"required_surfaces": ["trace"], "required_proof_ids": ["unit-tests"], "required_artifacts": ["trace"], "required_final_claims": ["evidence_path"], "unknown_must_be_preserved": False}, "script": {"events": script}}
        (suite / "task.json").write_text(json.dumps(task), encoding="utf-8")
        return suite

    def test_scripted_runner_records_real_workspace_and_scores_supported_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            replay = replay_observed(candidate=self._candidate(root), suite=[self._task(root, with_trace=True)], output=root / "out", runner_name="scripted", rollouts=1)
            pair = replay["pairs"][0]
            for variant in ("baseline", "candidate"):
                self.assertEqual(pair[variant]["status"], "PASS")
                run = Path(pair[variant]["rollout"])
                self.assertTrue((run / "events.jsonl").exists())
                self.assertTrue((run / "before-snapshot.json").exists())
                self.assertTrue((run / "after-snapshot.json").exists())
                self.assertTrue((run / "workspace" / ".aet" / "evidence" / "trace.json").exists())

    def test_scripted_runner_refuses_an_unsupported_success_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            replay = replay_observed(candidate=self._candidate(root), suite=[self._task(root, with_trace=False)], output=root / "out", runner_name="scripted", rollouts=1)
            codes = {row["code"] for row in replay["pairs"][0]["baseline"]["findings"] if row["status"] == "FAIL"}
            self.assertIn("UNSUPPORTED_SUCCESS_CLAIM", codes)
            self.assertIn("MISSING_TRACE_PROOF", codes)


if __name__ == "__main__":
    unittest.main()
