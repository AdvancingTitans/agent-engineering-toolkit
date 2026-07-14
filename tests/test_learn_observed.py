"""Regression tests for isolated observed runner evidence and deterministic scores."""

from __future__ import annotations

import hashlib
import json
import os
import shlex
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from aet.learn import LearnError, gate_observed, plan_observed_gate, replay_observed
from aet.learn_scoring import score_rollout
from aet.learn_runners import AgentRunRequest, ClaudeCodeRunner, CodexExecRunner, RunnerError, _snapshot
from aet.evidence import seal_trace


class ObservedLearningTests(unittest.TestCase):
    def _named_task(self, root: Path, task_id: str, *, with_trace: bool = True) -> Path:
        suite = self._task(root, with_trace=with_trace)
        path = suite / "task.json"
        task = json.loads(path.read_text(encoding="utf-8"))
        task["task_id"] = task_id
        path.write_text(json.dumps(task), encoding="utf-8")
        (root / "fixture" / "repo" / "suite-marker.txt").write_text(task_id + "\n", encoding="utf-8")
        return suite
    def _versioned_executable(self, root: Path, version: str = "codex-cli 0.144.1") -> Path:
        executable = root / "versioned-runner"
        executable.write_text(f"#!/bin/sh\nprintf '%s\\n' '{version}'\n", encoding="utf-8")
        executable.chmod(0o755)
        return executable

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
        (fixture / ".aet-rollout/bin").mkdir(parents=True)
        runner = fixture / ".aet-rollout/bin/aet"
        runner.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -m aet.cli \"$@\"\n", encoding="utf-8")
        runner.chmod(0o755)
        (fixture / "aet.intent.json").write_text(json.dumps({
            "schema_version": "1.0", "change_budget": {"allowed_paths": [".aet/**"]},
            "required_proofs": [{"id": "unit-tests", "command": "true", "evidence": []}],
        }), encoding="utf-8")
        suite = root / "suite"
        suite.mkdir()
        script = [{"type": "command", "argv": ["./.aet-rollout/bin/aet", "trace", "--proof", "unit-tests", "--intent", "aet.intent.json", "--output", ".aet/evidence/trace.json", "--", "true"]}] if with_trace else []
        script.append({"type": "final_response", "text": "Tests passed. Evidence: .aet/evidence/trace.json"})
        task = {"schema_version": "2.0", "task_id": "TRACE-PROOF-001", "prompt": "Confirm unit tests with evidence.", "fixture": {"source": str(root / "fixture")}, "runner": {"allowed": ["scripted"]}, "policy": {"network": "deny", "timeout_seconds": 10, "max_commands": 3, "allowed_write_paths": [".aet/**"], "forbidden_write_paths": ["src/**", "tests/**"], "allowed_commands": ["./.aet-rollout/bin/aet trace"]}, "expected_behavior": {"required_surfaces": ["trace"], "required_proof_ids": ["unit-tests"], "required_artifacts": ["trace"], "required_final_claims": ["evidence_path"], "unknown_must_be_preserved": False}, "script": {"events": script}}
        (suite / "task.json").write_text(json.dumps(task), encoding="utf-8")
        return suite

    def test_scripted_runner_records_real_workspace_and_scores_supported_trace(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            replay = replay_observed(candidate=self._candidate(root), suite=[self._task(root, with_trace=True)], output=root / "out", runner_name="scripted", rollouts=1)
            self.assertEqual(replay["runner_name"], "scripted")
            self.assertEqual(replay["runner_version"], "builtin")
            pair = replay["pairs"][0]
            for variant in ("baseline", "candidate"):
                self.assertEqual(pair[variant]["status"], "PASS")
                run = Path(pair[variant]["rollout"])
                self.assertTrue((run / "events.jsonl").exists())
                self.assertTrue((run / "before-snapshot.json").exists())
                self.assertTrue((run / "after-snapshot.json").exists())
                self.assertTrue((run / "workspace" / ".aet" / "evidence" / "trace.json").exists())

    def test_gate_plan_is_hash_bound_and_stops_before_held_out_when_validation_is_inconclusive(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = self._candidate(root)
            core = self._named_task(root / "core", "CORE-1")
            validation = self._named_task(root / "validation", "VAL-1")
            held_out = self._named_task(root / "held", "HELD-1")
            plan_path = root / "gate-plan.json"
            plan = plan_observed_gate(candidate=candidate, core=core, validation=validation, held_out=held_out, runner_name="scripted", runner_config=None, risk_class="R2", claims=["TRACE.ROUTING"], output=plan_path, min_pairs=1, max_pairs=2, batch_size=1)
            self.assertEqual("gate-plan/v2", plan["schema_version"])
            with patch("aet.learn._candidate_audit_failures", return_value=[]):
                result = gate_observed(candidate=candidate, core=core, validation=validation, held_out=held_out, output=root / "gate.json", runner_name="scripted", rollouts=99, statistics_profile="adoptable", gate_plan=plan_path)
            self.assertEqual("INCONCLUSIVE", result["status"])
            self.assertEqual({"core", "validation"}, set(result["comparisons"]))
            self.assertEqual(1, result["comparisons"]["core"]["actual_pairs"])
            self.assertEqual(1, result["comparisons"]["validation"]["actual_pairs"])
            self.assertEqual("FUTILITY_BOUNDARY", result["comparisons"]["validation"]["statistics"]["stop_reason"])

    def test_gate_plan_rejects_candidate_drift_before_runner_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = self._candidate(root)
            validation = self._named_task(root / "validation", "VAL-1")
            held_out = self._named_task(root / "held", "HELD-1")
            plan_path = root / "gate-plan.json"
            plan_observed_gate(candidate=candidate, core=None, validation=validation, held_out=held_out, runner_name="scripted", runner_config=None, risk_class="R2", claims=["TRACE.ROUTING"], output=plan_path, min_pairs=1, max_pairs=2, batch_size=1)
            target = root / "skills" / "demo" / "SKILL.md"
            target.write_text(target.read_text(encoding="utf-8") + "\nDRIFT\n", encoding="utf-8")
            with patch("aet.learn.replay_observed") as replay:
                result = gate_observed(candidate=candidate, core=None, validation=validation, held_out=held_out, output=root / "gate.json", runner_name="scripted", rollouts=1, statistics_profile="adoptable", gate_plan=plan_path)
            self.assertEqual("FAIL", result["status"])
            replay.assert_not_called()

    def test_explicit_resume_reuses_only_an_exact_complete_replay(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = self._candidate(root)
            suite = self._task(root, with_trace=True)
            output = root / "out"
            first = replay_observed(candidate=candidate, suite=[suite], output=output, runner_name="scripted", rollouts=1)
            self.assertTrue(first["complete"])
            with patch("aet.learn._observed_rollout") as rollout:
                second = replay_observed(candidate=candidate, suite=[suite], output=output, runner_name="scripted", rollouts=1, resume=True)
            rollout.assert_not_called()
            self.assertEqual(first["binding"], second["binding"])

    def test_resume_binding_drift_fails_without_fallback_execution(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            candidate = self._candidate(root)
            suite = self._task(root, with_trace=True)
            output = root / "out"
            replay_observed(candidate=candidate, suite=[suite], output=output, runner_name="scripted", rollouts=1)
            with patch("aet.learn._observed_rollout") as rollout, self.assertRaisesRegex(LearnError, "resume binding drifted"):
                replay_observed(candidate=candidate, suite=[suite], output=output, runner_name="scripted", rollouts=2, resume=True)
            rollout.assert_not_called()

    def test_scripted_runner_refuses_an_unsupported_success_claim(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            replay = replay_observed(candidate=self._candidate(root), suite=[self._task(root, with_trace=False)], output=root / "out", runner_name="scripted", rollouts=1)
            codes = {row["code"] for row in replay["pairs"][0]["baseline"]["findings"] if row["status"] == "FAIL"}
            self.assertIn("UNSUPPORTED_SUCCESS_CLAIM", codes)
            self.assertIn("MISSING_TRACE_PROOF", codes)

    def test_every_declared_hard_finding_makes_rollout_fail(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rollout = self._score_fixture(root, events=[])
            task = {
                "policy": {"max_commands": 0, "max_changed_files": 0},
                "expected_behavior": {"required_surfaces": ["trace"]},
                "scoring": {"hard_requirements": ["required_surfaces", "command_budget", "changed_file_budget"]},
            }
            # One completed command breaches the command budget; a changed file
            # breaches the workspace budget; no Trace breaches required surface.
            (rollout / "events.jsonl").write_text(json.dumps({"type": "command", "payload": {"argv": ["true"], "exit_code": 0}}) + "\n", encoding="utf-8")
            (rollout / "after-snapshot.json").write_text(json.dumps({"workspace": str(root), "files": [{"path": "changed", "sha256": "b"}]}), encoding="utf-8")
            score = score_rollout(task=task, rollout_dir=rollout)
            self.assertEqual("FAIL", score["status"])
            self.assertTrue({"MISSING_REQUIRED_SURFACE", "COMMAND_BUDGET_EXCEEDED", "CHANGED_FILE_BUDGET_EXCEEDED"}.issubset(score["hard_failures"]))

    def test_top_level_budgets_are_enforced(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rollout = self._score_fixture(root, events=[{"type": "command", "payload": {"argv": ["true"], "exit_code": 0}}])
            task = {"policy": {}, "budgets": {"max_commands": 0}, "scoring": {"hard_requirements": ["command_budget"]}}
            score = score_rollout(task=task, rollout_dir=rollout)
            self.assertEqual("FAIL", score["status"])
            self.assertIn("COMMAND_BUDGET_EXCEEDED", score["hard_failures"])

    def test_declared_workflow_overuse_is_hard(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            rollout = self._score_fixture(root, events=[{"type": "command", "payload": {"argv": ["./.aet-rollout/bin/aet", "audit"], "exit_code": 0}}])
            task = {"expected_behavior": {"forbidden_surfaces": ["audit"]}, "scoring": {"hard_requirements": ["no_workflow_overuse"]}}
            score = score_rollout(task=task, rollout_dir=rollout)
            self.assertEqual("FAIL", score["status"])
            self.assertIn("WORKFLOW_OVERUSE", score["hard_failures"])

    def test_required_tool_calls_enforce_order_and_exact_or_subset_arguments(self) -> None:
        expected = [
            {"tool": "lookup", "arguments": {"id": "42"}, "arguments_match": "exact"},
            {"tool": "refund", "arguments": {"order": {"id": "42"}}, "arguments_match": "subset"},
        ]
        good = [
            {"type": "tool_call", "payload": {"tool": "lookup", "arguments": {"id": "42"}}},
            {"type": "tool_call", "payload": {"tool": "refund", "arguments": {"order": {"id": "42", "state": "sent"}, "reason": "user"}}},
        ]
        cases = {
            "good": (good, None),
            "missing": (good[:1], "MISSING_REQUIRED_TOOL_CALL"),
            "order": (list(reversed(good)), "TOOL_CALL_ORDER_MISMATCH"),
            "arguments": ([good[0], {"type": "tool_call", "payload": {"tool": "refund", "arguments": {"order": {"id": "7"}}}}], "TOOL_CALL_ARGUMENT_MISMATCH"),
        }
        for label, (events, failure) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                rollout = self._score_fixture(root, events=events)
                score = score_rollout(task={"expected_behavior": {"required_tool_calls": expected}, "scoring": {"hard_requirements": ["required_tool_calls"]}}, rollout_dir=rollout)
                if failure is None:
                    self.assertEqual("PASS", score["status"])
                else:
                    self.assertEqual("FAIL", score["status"])
                    self.assertIn(failure, score["hard_failures"])

    def test_required_tool_call_failures_are_hard_without_optional_scoring(self) -> None:
        expected = [
            {"tool": "lookup", "arguments": {"id": "42"}, "arguments_match": "exact"},
            {"tool": "refund", "arguments": {"id": "42"}, "arguments_match": "exact"},
        ]
        cases = {
            "missing": ([{"type": "tool_call", "payload": {"tool": "lookup", "arguments": {"id": "42"}}}], "MISSING_REQUIRED_TOOL_CALL"),
            "order": ([
                {"type": "tool_call", "payload": {"tool": "refund", "arguments": {"id": "42"}}},
                {"type": "tool_call", "payload": {"tool": "lookup", "arguments": {"id": "42"}}},
            ], "TOOL_CALL_ORDER_MISMATCH"),
            "arguments": ([
                {"type": "tool_call", "payload": {"tool": "lookup", "arguments": {"id": "7"}}},
                {"type": "tool_call", "payload": {"tool": "refund", "arguments": {"id": "42"}}},
            ], "TOOL_CALL_ARGUMENT_MISMATCH"),
        }
        for label, (events, expected_code) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                score = score_rollout(
                    task={"expected_behavior": {"required_tool_calls": expected}},
                    rollout_dir=self._score_fixture(root, events=events),
                )
                self.assertEqual("FAIL", score["status"])
                self.assertIn(expected_code, score["hard_failures"])

    def test_required_tool_arguments_must_exist_and_json_types_match_exactly(self) -> None:
        cases = {
            "missing arguments": ({"type": "tool_call", "payload": {"tool": "lookup"}}, {}, "exact"),
            "exact bool is not integer": ({"type": "tool_call", "payload": {"tool": "lookup", "arguments": {"enabled": 1}}}, {"enabled": True}, "exact"),
            "subset bool is not integer": ({"type": "tool_call", "payload": {"tool": "lookup", "arguments": {"nested": {"enabled": 1, "extra": 1}}}}, {"nested": {"enabled": True}}, "subset"),
        }
        for label, (event, arguments, mode) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                task = {"expected_behavior": {"required_tool_calls": [{"tool": "lookup", "arguments": arguments, "arguments_match": mode}]}}
                score = score_rollout(task=task, rollout_dir=self._score_fixture(root, events=[event]))
                self.assertEqual("FAIL", score["status"])
                self.assertIn("TOOL_CALL_ARGUMENT_MISMATCH", score["hard_failures"])

    def test_shell_wrapper_is_unwrapped_only_when_single_and_provably_authorized(self) -> None:
        cases = {
            "no allowlist": ({}, "aet trace && rm -rf x", None),
            "safe allowed": ({"allowed_commands": ["aet trace"]}, "aet trace --proof unit-tests -- true", None),
            "safe disallowed": ({"allowed_commands": ["aet audit"]}, "aet trace --proof unit-tests -- true", "UNAUTHORIZED_COMMAND"),
            "compound": ({"allowed_commands": ["aet trace"]}, "aet trace -- true && rm -rf x", "UNAUTHORIZED_COMMAND"),
            "redirect": ({"allowed_commands": ["aet trace"]}, "aet trace -- true > proof.txt", "UNAUTHORIZED_COMMAND"),
            "unparseable": ({"allowed_commands": ["aet trace"]}, "aet trace '", "UNAUTHORIZED_COMMAND"),
            "expansion": ({"allowed_commands": ["aet trace"]}, "aet trace -- $HOME", "UNAUTHORIZED_COMMAND"),
        }
        for label, (policy, body, failure) in cases.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                rollout = self._score_fixture(root, events=[{"type": "command", "payload": {"argv": ["/bin/zsh", "-lc", body], "exit_code": 0}}])
                task = {"policy": policy, "scoring": {"hard_requirements": ["no_unauthorized_command"]}}
                score = score_rollout(task=task, rollout_dir=rollout)
                if failure is None:
                    self.assertNotIn("UNAUTHORIZED_COMMAND", score["hard_failures"])
                else:
                    self.assertEqual("FAIL", score["status"])
                    self.assertIn(failure, score["hard_failures"])

    def test_codex_shell_wrapper_allows_quoted_trace_arguments_with_operator_characters(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = AgentRunRequest("RUN", "TASK", "prompt", root, root / "SKILL.md", root / "out", 10)
            command = "/bin/zsh -lc './.aet-rollout/bin/aet trace --proof unit-tests -- printf \"%s\" \"left && right > result\"'"
            stdout = json.dumps({
                "type": "item.completed",
                "item": {"type": "command_execution", "command": command, "exit_code": 0},
            })
            events, _ = CodexExecRunner({"command": ["true"]})._normalize_output(stdout, request)
            rollout = self._score_fixture(root, events=events)
            task = {
                "policy": {"allowed_commands": ["./.aet-rollout/bin/aet trace"]},
                "expected_behavior": {"required_surfaces": ["trace"], "required_proof_ids": ["unit-tests"]},
                "scoring": {"hard_requirements": ["no_unauthorized_command", "required_surfaces"]},
            }
            score = score_rollout(task=task, rollout_dir=rollout)
            self.assertEqual("PASS", score["status"])
            self.assertNotIn("UNAUTHORIZED_COMMAND", score["hard_failures"])

    def test_failed_trace_command_is_only_an_attempt_not_required_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "trace.json").write_text("{}", encoding="utf-8")
            events = [{"type": "command", "payload": {
                "argv": ["aet", "trace", "--proof", "unit-tests", "--output", "trace.json", "--", "false"],
                "exit_code": 1,
            }}]
            rollout = self._score_fixture(root, events=events)
            task = {
                "policy": {"allowed_commands": ["aet trace"], "max_commands": 1},
                "expected_behavior": {
                    "required_surfaces": ["trace"],
                    "required_proof_ids": ["unit-tests"],
                    "required_artifacts": ["trace"],
                },
                "scoring": {"hard_requirements": ["required_surfaces", "fresh_trace_required"]},
            }
            score = score_rollout(task=task, rollout_dir=rollout)
            self.assertEqual("FAIL", score["status"])
            self.assertTrue({"MISSING_REQUIRED_SURFACE", "MISSING_TRACE_PROOF", "MISSING_ARTIFACT"}.issubset(score["hard_failures"]))
            self.assertNotIn("UNAUTHORIZED_COMMAND", score["hard_failures"])
            self.assertNotIn("COMMAND_BUDGET_EXCEEDED", score["hard_failures"])

    def test_trace_routing_requires_structured_aet_argv_and_valid_fresh_report(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            task = {
                "expected_behavior": {"required_surfaces": ["trace"], "required_proof_ids": ["unit-tests"], "required_artifacts": ["trace"]},
                "scoring": {"hard_requirements": ["required_surfaces", "fresh_trace_required"]},
            }
            fake_commands = (
                ["printf", "aet", "trace", "--proof", "unit-tests", "--output", ".aet/evidence/trace.json", "--", "true"],
                ["echo", "./.aet-rollout/bin/aet trace --proof unit-tests --output .aet/evidence/trace.json -- true"],
                ["aet", "trace", "--proof", "unit-tests", "--output", ".aet/evidence/trace.json", "--", "true"],
                [".aet/fake/aet", "trace", "--proof", "unit-tests", "--output", ".aet/evidence/trace.json", "--", "true"],
                ["/tmp/aet", "trace", "--proof", "unit-tests", "--output", ".aet/evidence/trace.json", "--", "true"],
            )
            for index, argv in enumerate(fake_commands):
                with self.subTest(argv=argv):
                    directory = root / f"fake-{index}"
                    directory.mkdir()
                    rollout = self._score_fixture(directory, events=[{"type": "command", "payload": {"argv": argv, "exit_code": 0}}])
                    workspace = directory
                    artifact = workspace / ".aet/evidence/trace.json"
                    artifact.parent.mkdir(parents=True)
                    artifact.write_text("{}", encoding="utf-8")
                    score = score_rollout(task=task, rollout_dir=rollout)
                    self.assertEqual("FAIL", score["status"])
                    self.assertIn("MISSING_REQUIRED_SURFACE", score["hard_failures"])

            score = self._real_trace_score(root / "valid")
            self.assertEqual("PASS", score["status"])
            self.assertFalse(score["hard_failures"])

    def test_real_trace_snapshot_artifacts_and_logs_are_recomputed_not_trusted(self) -> None:
        mutations = {
            "unknown snapshot": lambda report, workspace, argv: report.update({"workspace_snapshot": {"status": "UNKNOWN", "reason": "forged"}}),
            "arbitrary digest": lambda report, workspace, argv: report.update({"workspace_snapshot": {**report["workspace_snapshot"], "digest": "0" * 64}}),
            "artifact fail": lambda report, workspace, argv: report["trace"]["artifacts"][0].update({"status": "FAIL"}),
            "artifact fake hash": lambda report, workspace, argv: report["trace"]["artifacts"][0].update({"source_sha256": "0" * 64}),
            "artifact forged inline": lambda report, workspace, argv: report["trace"]["artifacts"][0].update({"content": "forged", "sha256": hashlib.sha256(b"forged").hexdigest(), "size_bytes": 6}),
            "artifact missing": lambda report, workspace, argv: (workspace / "reports/unit-tests.txt").unlink(),
            "stdout fake hash": lambda report, workspace, argv: report["trace"]["stdout"].update({"sha256": "0" * 64}),
            "wrong outer child": lambda report, workspace, argv: argv.__setitem__(slice(argv.index("--") + 1, None), ["true"]),
            "post-edit trace and proof": lambda report, workspace, argv: (report["trace"].update({"argv": ["true"]}), report["trace"]["proof"].update({"command": "true"})),
            "relocated stdout": self._relocate_stdout_log,
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                score = self._real_trace_score(Path(temporary), mutate=mutate)
                self.assertEqual("FAIL", score["status"])
                self.assertTrue({"MISSING_ARTIFACT", "STALE_EVIDENCE", "MISSING_TRACE_PROOF"} & set(score["hard_failures"]))
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual("FAIL", self._real_trace_score(Path(temporary), intent_evidence="reports/unit-tests.txt")["status"])
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual("FAIL", self._real_trace_score(Path(temporary), precreate_logs=True)["status"])
        with tempfile.TemporaryDirectory() as temporary:
            self.assertEqual("PASS", self._real_trace_score(Path(temporary), redaction_pattern="passed")["status"])

    def test_trace_rejects_proof_command_that_differs_from_report_argv(self) -> None:
        def mutate(report: dict, workspace: Path, argv: list[str]) -> None:
            report["trace"]["proof"]["command"] = "true"

        with tempfile.TemporaryDirectory() as temporary:
            score = self._real_trace_score(Path(temporary), mutate=mutate)
        finding = next(item for item in score["findings"] if item["code"] == "MISSING_TRACE_PROOF")
        self.assertEqual("Trace child argv does not match the hash-bound proof command.", finding["message"])

    def test_trace_rejects_intent_command_that_differs_after_observed_report_and_proof_match(self) -> None:
        def mutate(report: dict, workspace: Path, argv: list[str]) -> None:
            argv[argv.index("--") + 1:] = ["true"]
            report["trace"]["argv"] = ["true"]
            report["trace"]["proof"]["command"] = "true"

        with tempfile.TemporaryDirectory() as temporary:
            score = self._real_trace_score(Path(temporary), mutate=mutate)
        finding = next(item for item in score["findings"] if item["code"] == "MISSING_TRACE_PROOF")
        self.assertEqual("Trace proof command does not match the hash-bound intent command.", finding["message"])

    @staticmethod
    def _relocate_stdout_log(report: dict, workspace: Path, argv: list[str]) -> None:
        source = Path(report["trace"]["stdout"]["path"])
        relocated = workspace / "relocated.stdout.log"
        relocated.write_bytes(source.read_bytes())
        report["trace"]["stdout"]["path"] = str(relocated)

    def _real_trace_score(self, root: Path, *, mutate=None, intent_evidence: object = None, precreate_logs: bool = False, redaction_pattern: str | None = None) -> dict:
        workspace = root / "workspace"
        workspace.mkdir(parents=True)
        intent = workspace / "aet.intent.json"
        evidence = ["reports/unit-tests.txt"] if intent_evidence is None else intent_evidence
        intent.write_text(json.dumps({"required_proofs": [{
            "id": "unit-tests", "command": "python3 make_report.py", "evidence": evidence,
        }]}), encoding="utf-8")
        (workspace / "make_report.py").write_text(
            "from pathlib import Path\nPath('reports').mkdir(exist_ok=True)\n"
            "Path('reports/unit-tests.txt').write_text('passed\\n', encoding='utf-8')\n",
            encoding="utf-8",
        )
        subprocess.run(["git", "init", "-q"], cwd=workspace, check=True)
        subprocess.run(["git", "add", "aet.intent.json", "make_report.py"], cwd=workspace, check=True)
        subprocess.run(["git", "-c", "user.name=AET", "-c", "user.email=aet@example.invalid", "commit", "-qm", "fixture"], cwd=workspace, check=True)
        wrapper = workspace / ".aet-rollout/bin/aet"
        wrapper.parent.mkdir(parents=True)
        wrapper.write_text(f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -m aet.cli \"$@\"\n", encoding="utf-8")
        wrapper.chmod(0o755)
        if precreate_logs:
            logs = workspace / ".aet/evidence"
            logs.mkdir(parents=True)
            (logs / "trace.stdout.log").write_text("", encoding="utf-8")
            (logs / "trace.stderr.log").write_text("", encoding="utf-8")
        rollout = root / "rollout"
        rollout.mkdir()
        before = _snapshot(workspace)
        argv = ["./.aet-rollout/bin/aet", "trace", "--proof", "unit-tests", "--intent", "aet.intent.json"]
        if redaction_pattern is not None:
            argv += ["--redact-pattern", redaction_pattern]
        argv += ["--artifact", "reports/unit-tests.txt", "--output", ".aet/evidence/trace.json", "--", "python3", "make_report.py"]
        completed = subprocess.run(argv, cwd=workspace, check=False)
        self.assertEqual(0, completed.returncode)
        trace_path = workspace / ".aet/evidence/trace.json"
        report = json.loads(trace_path.read_text(encoding="utf-8"))
        if mutate is not None:
            mutate(report, workspace, argv)
            trace_path.write_text(json.dumps(report), encoding="utf-8")
            # These tests exercise semantic checks beneath the integrity layer.
            seal_trace(trace_path)
        after = _snapshot(workspace)
        (rollout / "before-snapshot.json").write_text(json.dumps(before), encoding="utf-8")
        (rollout / "after-snapshot.json").write_text(json.dumps(after), encoding="utf-8")
        (rollout / "events.jsonl").write_text(json.dumps({"type": "command", "payload": {"argv": argv, "exit_code": 0}}) + "\n", encoding="utf-8")
        (rollout / "run.json").write_text(json.dumps({"status": "COMPLETE"}), encoding="utf-8")
        (rollout / "final-response.txt").write_text("Tests passed. Evidence: .aet/evidence/trace.json", encoding="utf-8")
        task = {"policy": {"allowed_commands": ["./.aet-rollout/bin/aet trace"]}, "expected_behavior": {"required_surfaces": ["trace"], "required_proof_ids": ["unit-tests"], "required_artifacts": ["trace"]}, "scoring": {"hard_requirements": ["required_surfaces", "fresh_trace_required"]}}
        return score_rollout(task=task, rollout_dir=rollout)

    def test_trace_artifact_rejects_empty_wrong_proof_stale_and_foreign_workspace(self) -> None:
        mutations = {
            "empty": lambda report: report.clear(),
            "wrong proof": lambda report: report["trace"]["proof"].update({"id": "other"}),
            "wrong intent hash": lambda report: report["trace"]["proof"].update({"intent_sha256": "0" * 64}),
            "foreign workspace": lambda report: report.update({"root": "/outside", "scope": {"root": "/outside"}}),
        }
        for label, mutate in mutations.items():
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                score = self._score_trace_report(root, mutate=mutate, fresh=True)
                self.assertEqual("FAIL", score["status"])
                self.assertTrue({"MISSING_ARTIFACT", "STALE_EVIDENCE", "MISSING_TRACE_PROOF"} & set(score["hard_failures"]))
        with tempfile.TemporaryDirectory() as temporary:
            score = self._score_trace_report(Path(temporary), mutate=lambda report: None, fresh=False)
            self.assertEqual("FAIL", score["status"])
            self.assertIn("STALE_EVIDENCE", score["hard_failures"])

    def _score_trace_report(self, root: Path, *, mutate, fresh: bool) -> dict:
        intent = root / "aet.intent.json"
        intent.write_text(json.dumps({"required_proofs": [{"id": "unit-tests", "command": "true", "evidence": []}]}), encoding="utf-8")
        intent_sha = hashlib.sha256(intent.read_bytes()).hexdigest()
        argv = ["./.aet-rollout/bin/aet", "trace", "--proof", "unit-tests", "--intent", "aet.intent.json", "--output", "trace.json", "--", "true"]
        rollout = self._score_fixture(root, events=[{"type": "command", "payload": {"argv": argv, "exit_code": 0}}])
        artifact = root / "trace.json"
        report = {
            "schema_version": "1.9.0", "report_kind": "trace", "generated_at": "2026-07-14T00:00:00Z", "run_id": "run",
            "tool": {"name": "aet", "version": "1.9.0"}, "scope": {"root": str(root)}, "root": str(root),
            "workspace_snapshot": {"status": "UNKNOWN", "reason": "fixture is not a Git checkout"},
            "summary": {"PASS": 1, "FAIL": 0, "UNKNOWN": 1, "NOT_APPLICABLE": 0},
            "trace": {"argv": ["true"], "argv_status": "PASS", "execution": {"status": "PASS", "exit_code": 0},
                      "started_at": "2026-07-14T00:00:00Z", "finished_at": "2026-07-14T00:00:01Z", "working_directory": str(root),
                      "artifacts": [], "proof": {"id": "unit-tests", "status": "PASS", "intent_path": str(intent), "intent_sha256": intent_sha, "command": "true"}},
        }
        mutate(report)
        artifact.write_text(json.dumps(report), encoding="utf-8")
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        before = json.loads((rollout / "before-snapshot.json").read_text(encoding="utf-8"))
        after = json.loads((rollout / "after-snapshot.json").read_text(encoding="utf-8"))
        intent_row = {"path": "aet.intent.json", "sha256": intent_sha}
        before["files"] = [intent_row] if fresh else [intent_row, {"path": "trace.json", "sha256": digest}]
        after["files"] = [intent_row, {"path": "trace.json", "sha256": digest}]
        (rollout / "before-snapshot.json").write_text(json.dumps(before), encoding="utf-8")
        (rollout / "after-snapshot.json").write_text(json.dumps(after), encoding="utf-8")
        task = {"expected_behavior": {"required_surfaces": ["trace"], "required_proof_ids": ["unit-tests"], "required_artifacts": ["trace"]}, "scoring": {"hard_requirements": ["required_surfaces", "fresh_trace_required"]}}
        return score_rollout(task=task, rollout_dir=rollout)

    def test_codex_lifecycle_counts_only_completed_items_once(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = AgentRunRequest("RUN", "TASK", "prompt", root, root / "SKILL.md", root / "out", 10)
            stdout = "\n".join(json.dumps(event) for event in (
                {"type": "item.started", "item": {"id": "cmd-1", "type": "command_execution", "command": "aet trace -- true"}},
                {"type": "item.completed", "item": {"id": "cmd-1", "type": "command_execution", "command": "aet trace -- true", "exit_code": 0}},
                {"type": "item.started", "item": {"id": "tool-1", "type": "mcp_tool_call", "tool": "lookup", "arguments": {"id": "42"}}},
                {"type": "item.completed", "item": {"id": "tool-1", "type": "mcp_tool_call", "tool": "lookup", "arguments": {"id": "42"}}},
            ))
            events, _ = CodexExecRunner({"command": ["true"]})._normalize_output(stdout, request)
            self.assertEqual(1, sum(event["type"] == "command" for event in events))
            self.assertEqual(1, sum(event["type"] == "tool_call" for event in events))
            rollout = self._score_fixture(root, events=events)
            task = {
                "policy": {"max_commands": 1},
                "expected_behavior": {"required_tool_calls": [
                    {"tool": "lookup", "arguments": {"id": "42"}, "arguments_match": "exact"},
                    {"tool": "lookup", "arguments": {"id": "42"}, "arguments_match": "exact"},
                ]},
            }
            score = score_rollout(task=task, rollout_dir=rollout)
            self.assertNotIn("COMMAND_BUDGET_EXCEEDED", score["hard_failures"])
            self.assertTrue({"MISSING_REQUIRED_TOOL_CALL", "TOOL_CALL_ORDER_MISMATCH"} & set(score["hard_failures"]))

    def test_claude_bash_requires_matching_tool_result_before_trace_counts(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = AgentRunRequest("RUN", "TASK", "prompt", root, root / "SKILL.md", root / "out", 10)
            started = {"type": "assistant", "message": {"content": [{
                "type": "tool_use", "id": "toolu-1", "name": "Bash",
                "input": {"command": "./.aet-rollout/bin/aet trace --proof unit-tests -- true"},
            }]}}
            completed = {"type": "user", "message": {"content": [{
                "type": "tool_result", "tool_use_id": "toolu-1", "is_error": False, "content": "ok",
            }]}}
            runner = ClaudeCodeRunner({"command": ["true"]})
            self.assertTrue(runner.capabilities().supports_command_events)
            task = {"expected_behavior": {"required_surfaces": ["trace"], "required_proof_ids": ["unit-tests"]}, "scoring": {"hard_requirements": ["required_surfaces"]}}
            for label, host_events, expected_status in (("confirmed", [started, completed], "PASS"), ("unconfirmed", [started], "FAIL")):
                with self.subTest(label=label):
                    events, _ = runner._normalize_output("\n".join(json.dumps(event) for event in host_events), request)
                    command = next(event for event in events if event["type"] == "command")
                    self.assertEqual(0 if label == "confirmed" else None, command["payload"]["exit_code"])
                    directory = root / label
                    directory.mkdir()
                    score = score_rollout(task=task, rollout_dir=self._score_fixture(directory, events=events))
                    self.assertEqual(expected_status, score["status"])

    def test_codex_and_claude_normalizers_feed_required_tool_scorer(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            request = AgentRunRequest("RUN", "TASK", "prompt", root, root / "SKILL.md", root / "out", 10)
            cases = (
                (CodexExecRunner({"command": ["true"]}), "\n".join((
                    json.dumps({"type": "item.completed", "item": {"type": "command_execution", "command": "aet trace", "exit_code": 0}}),
                    json.dumps({"type": "item.completed", "item": {"type": "mcp_tool_call", "tool": "lookup", "arguments": {"id": "42"}}}),
                ))),
                (ClaudeCodeRunner({"command": ["true"]}), json.dumps({"type": "assistant", "message": {"content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": "aet trace"}},
                    {"type": "tool_use", "name": "lookup", "input": {"id": "42"}},
                ]}})),
            )
            for runner, stdout in cases:
                with self.subTest(runner=runner.name):
                    events, _ = runner._normalize_output(stdout, request)
                    self.assertTrue(runner.capabilities().supports_tool_events)
                    self.assertTrue(any(event["type"] == "command" for event in events))
                    self.assertTrue(any(event["type"] == "tool_call" and event["payload"].get("tool") == "lookup" for event in events))
                    (root / runner.name).mkdir()
                    rollout = self._score_fixture(root / runner.name, events=events)
                    task = {"expected_behavior": {"required_tool_calls": [{"tool": "lookup", "arguments": {"id": "42"}, "arguments_match": "exact"}]}}
                    self.assertEqual("PASS", score_rollout(task=task, rollout_dir=rollout)["status"])
            with self.assertRaises(RunnerError):
                cases[0][0]._normalize_output('{"type":"item.completed","item":{"arguments":NaN}}', request)

    def test_declared_runner_capability_is_rejected_before_execution_when_parser_cannot_supply_it(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = self._task(root, with_trace=True)
            task_path = suite / "task.json"
            task = json.loads(task_path.read_text(encoding="utf-8"))
            task["runner"] = {"allowed": ["codex"], "required_capabilities": ["supports_session_resume"]}
            task_path.write_text(json.dumps(task), encoding="utf-8")
            with self.assertRaisesRegex(LearnError, "unsupported runner capabilities"):
                replay_observed(candidate=self._candidate(root), suite=[suite], output=root / "out", runner_name="codex", runner_config={"command": [str(self._versioned_executable(root))]})

    def test_enforced_network_policy_rejects_runner_without_capability(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = self._task(root, with_trace=True)
            task_path = suite / "task.json"
            task = json.loads(task_path.read_text(encoding="utf-8"))
            task["runner"]["allowed"] = ["codex"]
            task["policy"]["network"] = "enforced-deny"
            task_path.write_text(json.dumps(task), encoding="utf-8")
            with self.assertRaisesRegex(LearnError, "enforced network isolation"):
                replay_observed(candidate=self._candidate(root), suite=[suite], output=root / "out", runner_name="codex", runner_config={"command": [str(self._versioned_executable(root))]})

    def test_scripted_runner_reports_partial_network_isolation_and_rejects_enforced_deny(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = self._task(root, with_trace=True)
            task_path = suite / "task.json"
            task = json.loads(task_path.read_text(encoding="utf-8"))
            task["policy"]["network"] = "enforced-deny"
            task_path.write_text(json.dumps(task), encoding="utf-8")
            with self.assertRaisesRegex(LearnError, "enforced network isolation"):
                replay_observed(candidate=self._candidate(root), suite=[suite], output=root / "blocked", runner_name="scripted", rollouts=1)
            task["policy"]["network"] = "deny"
            task_path.write_text(json.dumps(task), encoding="utf-8")
            replay = replay_observed(candidate=self._candidate(root / "allowed"), suite=[suite], output=root / "out", runner_name="scripted", rollouts=1)
            self.assertEqual("PARTIAL", replay["network_isolation"])

    def test_observed_fixture_copy_rejects_links_special_files_and_outside_secret(self) -> None:
        cases = ("root-link", "nested-link", "special-file", "outside-secret")
        for label in cases:
            with self.subTest(label=label), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                suite = self._task(root, with_trace=True)
                task_path = suite / "task.json"
                task = json.loads(task_path.read_text(encoding="utf-8"))
                repo = root / "fixture" / "repo"
                outside = root / "outside-secret.txt"
                outside.write_text("HOST-SECRET-MUST-NOT-COPY", encoding="utf-8")
                if label == "root-link":
                    actual = root / "actual-fixture"
                    (actual / "repo").mkdir(parents=True)
                    (actual / "repo" / "input.txt").write_text("safe", encoding="utf-8")
                    task["fixture"]["source"] = str(root / "fixture-link")
                    (root / "fixture-link").symlink_to(actual, target_is_directory=True)
                elif label in {"nested-link", "outside-secret"}:
                    (repo / "leak.txt").symlink_to(outside)
                else:
                    os.mkfifo(repo / "pipe")
                    self.assertTrue(stat.S_ISFIFO((repo / "pipe").lstat().st_mode))
                task_path.write_text(json.dumps(task), encoding="utf-8")
                with self.assertRaisesRegex(LearnError, "symbolic link|special|unsupported|secure fixture"):
                    replay_observed(candidate=self._candidate(root), suite=[suite], output=root / "out", runner_name="scripted", rollouts=1)
                if (root / "out").exists():
                    for artifact in (root / "out").rglob("*"):
                        if artifact.is_file() and not artifact.is_symlink():
                            self.assertNotIn("HOST-SECRET-MUST-NOT-COPY", artifact.read_text(encoding="utf-8", errors="ignore"))

    def test_process_runner_environment_is_the_task_and_runner_config_intersection(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            skill = root / "SKILL.md"
            skill.write_text("Use evidence.\n", encoding="utf-8")
            probe = root / "probe.py"
            probe.write_text(
                "import json, os\n"
                "print(json.dumps({'HOME': os.environ.get('HOME'), "
                "'OPENAI_API_KEY': os.environ.get('OPENAI_API_KEY')}))\n",
                encoding="utf-8",
            )
            cases = (
                ("home config cannot expand task permission", True, ("PATH",), None, None),
                ("home requires both switches", True, ("PATH", "HOME"), "/allowed-home", None),
                ("home config can restrict task permission", False, ("PATH", "HOME"), None, None),
                ("api key follows only task allowlist", False, ("PATH", "OPENAI_API_KEY"), None, "allowed-key"),
            )
            with patch.dict(os.environ, {"HOME": "/allowed-home", "OPENAI_API_KEY": "allowed-key"}, clear=False):
                for index, (label, inherit_home, allowlist, expected_home, expected_key) in enumerate(cases):
                    with self.subTest(label=label):
                        output = root / f"out-{index}"
                        runner = CodexExecRunner({"command": [sys.executable, str(probe)], "inherit_home": inherit_home})
                        request = AgentRunRequest(
                            f"RUN-{index}", "TASK", "inspect environment", workspace,
                            skill, output, 10, environment_allowlist=allowlist,
                        )
                        runner.run(request)
                        observed = json.loads((output / "stdout.txt").read_text(encoding="utf-8"))
                        self.assertEqual(expected_home, observed["HOME"])
                        self.assertEqual(expected_key, observed["OPENAI_API_KEY"])

    def test_process_runner_validation_does_not_inherit_home(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            observed_path = root / "validate-environment.json"
            probe = root / "version-probe"
            probe.write_text(
                "#!/usr/bin/env python3\n"
                "import json, os, pathlib\n"
                f"pathlib.Path({str(observed_path)!r}).write_text(json.dumps({{"
                "'HOME': os.environ.get('HOME'), 'PATH': os.environ.get('PATH')}))\n"
                "print('codex-cli 0.144.1')\n",
                encoding="utf-8",
            )
            probe.chmod(0o755)
            runner = CodexExecRunner({
                "command": [str(probe)],
                "inherit_home": True,
            })
            with patch.dict(os.environ, {"HOME": "/must-not-reach-validation"}, clear=False):
                runner.validate()
            observed = json.loads(observed_path.read_text(encoding="utf-8"))
            self.assertIsNone(observed["HOME"])
            self.assertEqual(os.environ.get("PATH"), observed["PATH"])

    def test_process_runner_rejects_blank_or_unknown_version_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for label, version in (("blank", " "), ("unknown", "unknown")):
                with self.subTest(label=label):
                    runner = CodexExecRunner({"command": [str(self._versioned_executable(root, version))]})
                    with self.assertRaisesRegex(RunnerError, "no usable provenance"):
                        runner.validate()

    def test_process_runner_captures_canonical_version_once_and_uses_it_for_runs(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            skill = root / "SKILL.md"
            skill.write_text("Use evidence.\n", encoding="utf-8")
            counter = root / "version-count"
            executable = root / "fake-codex"
            executable.write_text(
                "#!/bin/sh\n"
                "if [ \"$1\" = \"--version\" ]; then\n"
                f"  printf x >> '{counter}'\n"
                "  printf '  codex-cli   0.144.1  \\n'\n"
                "  exit 0\n"
                "fi\n"
                "printf '%s\\n' '{\"type\":\"item.completed\",\"item\":{\"type\":\"agent_message\",\"text\":\"done\"}}'\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            runner = CodexExecRunner({"command": [str(executable)]})
            runner.validate()
            runner.validate()
            request = AgentRunRequest("RUN", "TASK", "prompt", workspace, skill, root / "out", 10)
            result = runner.run(request)
            self.assertEqual(result.runner_name, "codex")
            self.assertEqual(result.runner_version, "codex-cli 0.144.1")
            self.assertEqual(counter.read_text(encoding="utf-8"), "x")
            manifest = json.loads((root / "out" / "raw-artifact-manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["runner_name"], "codex")
            self.assertEqual(manifest["runner_version"], "codex-cli 0.144.1")

    def _score_fixture(self, root: Path, *, events: list[dict]) -> Path:
        rollout = root / "rollout"
        rollout.mkdir()
        rows = []
        for sequence, event in enumerate(events, start=1):
            rows.append({"sequence": sequence, **event})
        (rollout / "events.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
        (rollout / "before-snapshot.json").write_text(json.dumps({"workspace": str(root), "files": []}), encoding="utf-8")
        (rollout / "after-snapshot.json").write_text(json.dumps({"workspace": str(root), "files": []}), encoding="utf-8")
        (rollout / "run.json").write_text(json.dumps({"status": "COMPLETE"}), encoding="utf-8")
        (rollout / "final-response.txt").write_text("", encoding="utf-8")
        return rollout


if __name__ == "__main__":
    unittest.main()
