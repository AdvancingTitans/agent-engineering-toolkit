"""Deterministic business flows and delivery-gate contracts for v1.9."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import math
import os
import shlex
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

from aet.learn import harvest, replay_observed, verify_suite
from aet.learn_statistics import summarize_reliability


ROOT = Path(__file__).resolve().parents[1]
REAL_AGENT = ROOT / "eval" / "real-agent"


class BusinessQualityFlowsTests(unittest.TestCase):
    def _passing_observed_gate(self, candidate_sha256: str) -> dict[str, object]:
        statistics = {
            "report_kind": "learning_paired_statistics", "profile": "adoptable", "status": "PASS",
            "pair_count": 6, "usable_pair_count": 6, "infrastructure_pair_count": 0,
        }
        return {
            "report_kind": "learning_observed_gate", "status": "PASS", "runner": "codex",
            "runner_name": "codex", "runner_version": "codex-cli 0.144.1",
            "statistics_profile": "adoptable", "candidate_sha256": candidate_sha256,
            "hard_gate_failures": [], "candidate_audit_failures": [],
            "comparisons": {
                name: {"replay": f"replays/CAND-REAL-HOST-V1-9/{name}/observed-replay.json", "statistics": dict(statistics)}
                for name in ("core", "validation", "held_out")
            },
        }

    def _candidate(self, root: Path) -> Path:
        skill = root / "skills" / "business" / "SKILL.md"
        skill.parent.mkdir(parents=True)
        baseline = '<!-- aet-learn:immutable -->\nPreserve UNKNOWN.\n<!-- aet-learn:end -->\n<!-- aet-learn:editable id="flow" -->\nUse evidence.\n<!-- aet-learn:end -->\n'
        proposed = baseline.replace("Use evidence.", "Use fresh evidence and declared tools.")
        skill.write_text(baseline, encoding="utf-8")
        candidate = root / "candidate"
        candidate.mkdir()
        (candidate / "candidate.SKILL.md").write_text(proposed, encoding="utf-8")
        (candidate / "candidate.json").write_text(json.dumps({
            "candidate_id": "CAND-BUSINESS-FLOWS",
            "target_file": str(skill),
            "baseline_sha256": hashlib.sha256(baseline.encode()).hexdigest(),
            "candidate_sha256": hashlib.sha256(proposed.encode()).hexdigest(),
            "operations": [{
                "type": "replace_editable_block", "id": "flow",
                "before_sha256": hashlib.sha256(b"Use evidence.\n").hexdigest(),
                "new_text": "Use fresh evidence and declared tools.\n",
            }],
        }), encoding="utf-8")
        return candidate

    def test_deterministic_business_matrix_runs_real_scripted_replay_and_scores(self) -> None:
        expected = {
            "BUSINESS-PROOF-PASS": ("PASS", set()),
            "BUSINESS-REFUND-PASS": ("PASS", set()),
            "BUSINESS-REFUND-MISSING": ("FAIL", {"MISSING_REQUIRED_TOOL_CALL"}),
            "BUSINESS-REFUND-ORDER": ("FAIL", {"TOOL_CALL_ORDER_MISMATCH"}),
            "BUSINESS-REFUND-ARGS": ("FAIL", {"TOOL_CALL_ARGUMENT_MISMATCH"}),
            "BUSINESS-NONZERO-SUCCESS": ("FAIL", {"UNSUPPORTED_SUCCESS_CLAIM"}),
            "BUSINESS-NONZERO-UNKNOWN": ("PASS", set()),
            "BUSINESS-TIMEOUT-SUCCESS": ("FAIL", {"UNSUPPORTED_SUCCESS_CLAIM"}),
            "BUSINESS-STALE-TRACE": ("FAIL", {"STALE_EVIDENCE"}),
            "BUSINESS-SCOPE-WRITE": ("FAIL", {"SCOPE_VIOLATION"}),
            "BUSINESS-PRIVATE-OUTPUT": ("PASS", set()),
        }
        marker = "business-secret-never-export"
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            prior = os.environ.get("BUSINESS_SECRET")
            os.environ["BUSINESS_SECRET"] = marker
            try:
                replay = replay_observed(
                    candidate=self._candidate(root),
                    suite=[REAL_AGENT / "deterministic"],
                    output=root / "rollouts",
                    runner_name="scripted",
                    rollouts=6,
                    runner_config={"aet_argv": [sys.executable, "-m", "aet.cli"]},
                )
            finally:
                if prior is None:
                    os.environ.pop("BUSINESS_SECRET", None)
                else:
                    os.environ["BUSINESS_SECRET"] = prior

            self.assertEqual({pair["task_id"] for pair in replay["pairs"]}, set(expected))
            self.assertEqual(
                Counter(pair["task_id"] for pair in replay["pairs"]),
                Counter({task_id: 6 for task_id in expected}),
            )
            self.assertEqual(
                {pair["iteration"] for pair in replay["pairs"] if pair["task_id"] == "BUSINESS-PROOF-PASS"},
                set(range(6)),
            )
            for pair in replay["pairs"]:
                status, codes = expected[pair["task_id"]]
                for variant in ("baseline", "candidate"):
                    with self.subTest(task=pair["task_id"], variant=variant):
                        self.assertEqual(pair[variant]["status"], status)
                        failures = {item["code"] for item in pair[variant]["findings"] if item["status"] == "FAIL"}
                        self.assertTrue(codes <= failures)

            reliability = summarize_reliability(replay["pairs"])
            self.assertEqual(len(reliability["groups"]), len(expected) * 2)
            z = 1.959963984540054
            for row in reliability["groups"]:
                wanted_pass = expected[row["task_id"]][0] == "PASS"
                successes = 6 if wanted_pass else 0
                denominator = 1 + z * z / 6
                proportion = successes / 6
                center = (proportion + z * z / 12) / denominator
                margin = z * math.sqrt(proportion * (1 - proportion) / 6 + z * z / 144) / denominator
                with self.subTest(reliability=row["task_id"], variant=row["variant"]):
                    self.assertEqual(row["runs"], 6)
                    self.assertEqual(row["successes"], successes)
                    self.assertEqual(row["any_success"], wanted_pass)
                    self.assertEqual(row["all_success"], wanted_pass)
                    self.assertAlmostEqual(row["wilson_95"]["lower"], max(0, center - margin))
                    self.assertAlmostEqual(row["wilson_95"]["upper"], min(1, center + margin))

            proof_pair = next(pair for pair in replay["pairs"] if pair["task_id"] == "BUSINESS-PROOF-PASS")
            proof_report = Path(proof_pair["baseline"]["rollout"]) / "workspace" / "reports" / "unit-tests.txt"
            self.assertIn("test_total", proof_report.read_text(encoding="utf-8"))
            private_outputs = list((root / "rollouts").rglob("commands/*/stdout.txt"))
            self.assertTrue(any(marker in path.read_text(encoding="utf-8") for path in private_outputs))
            private_artifacts = list((root / "rollouts").rglob("workspace/reports/private-artifact.txt"))
            self.assertTrue(any(marker in path.read_text(encoding="utf-8") for path in private_artifacts))
            experiences = harvest(runs=None, evidence=root / "rollouts", output=root / "experiences.json")
            self.assertNotIn(marker, json.dumps(experiences, ensure_ascii=False))
            self.assertTrue(all(row["privacy"]["raw_transcript_retained"] is False for row in experiences["experiences"]))

            timeout_pairs = [pair for pair in replay["pairs"] if pair["task_id"] == "BUSINESS-TIMEOUT-SUCCESS"]
            self.assertEqual(len(timeout_pairs), 6)
            for pair in timeout_pairs:
                for variant in ("baseline", "candidate"):
                    rollout = Path(pair[variant]["rollout"])
                    command_output = next(rollout.glob("commands/*/stdout.txt")).read_text(encoding="utf-8")
                    events = [json.loads(line) for line in (rollout / "events.jsonl").read_text(encoding="utf-8").splitlines()]
                    command = next(event for event in events if event["type"] == "command")
                    run = json.loads((rollout / "run.json").read_text(encoding="utf-8"))
                    with self.subTest(timeout=pair["iteration"], variant=variant):
                        self.assertIn("TOOL_TIMEOUT", command_output)
                        self.assertIn("UNKNOWN", command_output)
                        self.assertEqual(command["payload"]["exit_code"], 124)
                        self.assertFalse(command["payload"]["timed_out"])
                        self.assertFalse(run["result"]["timed_out"])
                        self.assertEqual(pair[variant]["status"], "FAIL")

    def test_real_host_validation_and_held_out_suites_verify_and_use_independent_fixtures(self) -> None:
        suites = [REAL_AGENT / "core", REAL_AGENT / "validation", REAL_AGENT / "held-out", REAL_AGENT / "deterministic"]
        fixture_digests = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for suite in suites:
                result = verify_suite(suite=suite, output=root / f"{suite.name}.json")
                self.assertEqual(result["status"], "PASS", result["failures"])
                self.assertGreater(result["task_count"], 0)
            for fixture in ("python-proof", "python-proof-validation", "python-proof-held-out"):
                files = []
                for path in sorted((REAL_AGENT / "fixtures" / fixture).rglob("*")):
                    if path.is_file():
                        files.append((path.relative_to(REAL_AGENT / "fixtures" / fixture).as_posix(), hashlib.sha256(path.read_bytes()).hexdigest()))
                fixture_digests.append(hashlib.sha256(json.dumps(files).encode()).hexdigest())
        self.assertEqual(len(fixture_digests), len(set(fixture_digests)))

        for suite in (REAL_AGENT / "core", REAL_AGENT / "validation", REAL_AGENT / "held-out"):
            task = json.loads(next(suite.glob("*.json")).read_text(encoding="utf-8"))
            self.assertEqual(task["runner"]["allowed"], ["codex"])
            self.assertIn("trace", task["expected_behavior"]["required_surfaces"])
            self.assertEqual(task["expected_behavior"]["forbidden_surfaces"], ["audit", "review"])
            self.assertIn("no_workflow_overuse", task["scoring"]["hard_requirements"])
            self.assertTrue(task["expected_behavior"]["required_proof_ids"])
            self.assertIn("trace", task["expected_behavior"]["required_artifacts"])
            self.assertIn("fresh_trace_required", task["scoring"]["hard_requirements"])
            proof_id = task["expected_behavior"]["required_proof_ids"][0]
            self.assertIn(proof_id, task["prompt"])
            self.assertGreaterEqual(task["policy"]["max_commands"], 6)
            self.assertLessEqual(task["policy"]["max_commands"], 10)
            self.assertEqual(task["policy"]["allowed_commands"], ["./.aet-rollout/bin/aet trace"])
            self.assertEqual(set(task["policy"]["environment_allowlist"]), {"PATH", "HOME", "OPENAI_API_KEY"})
            fixture = (suite / task["fixture"]["source"]).resolve()
            intent = json.loads((fixture / "repo" / "aet.intent.json").read_text(encoding="utf-8"))
            self.assertEqual(intent["required_proofs"][0]["id"], proof_id)
            self.assertEqual(intent["required_proofs"][0]["command"], "python3 bin/run_proof.py")
            proof_runner = fixture / "repo" / "bin" / "run_proof.py"
            self.assertTrue(proof_runner.is_file())
            self.assertIn("PYTHONDONTWRITEBYTECODE", proof_runner.read_text(encoding="utf-8"))

    def test_tracked_candidate_builder_and_release_gate_recompute_content(self) -> None:
        builder = REAL_AGENT / "build_candidate.py"
        helper = REAL_AGENT / "release_gate.py"
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "candidate"
            subprocess.run(
                [sys.executable, str(builder), "--root", str(ROOT), "--output", str(output)],
                check=True,
            )
            metadata = json.loads((output / "candidate.json").read_text(encoding="utf-8"))
            candidate_bytes = (output / "candidate.SKILL.md").read_bytes()
            self.assertEqual(metadata["candidate_sha256"], hashlib.sha256(candidate_bytes).hexdigest())
            candidate_text = candidate_bytes.decode()
            for instruction in (
                "aet.intent.json", "./.aet-rollout/bin/aet trace", "--proof", "--intent",
                "--artifact", ".aet/evidence/trace.json", "python3 bin/run_proof.py",
                "use the proof id and report artifact named in the task prompt",
                "Do not run extra `aet audit` or `aet review` commands",
            ):
                self.assertIn(instruction, candidate_text)
            self.assertNotIn("read `aet.intent.json`", candidate_text)

            raw_gate = Path(temporary) / "raw-gate.json"
            raw_gate.write_text(json.dumps(self._passing_observed_gate(metadata["candidate_sha256"])), encoding="utf-8")
            manifest = Path(temporary) / "real-host-gate.json"
            common = [
                "--root", str(ROOT), "--candidate", str(output), "--raw-gate", str(raw_gate),
                "--commit", "a" * 40, "--version", "1.9.0",
            ]
            subprocess.run([sys.executable, str(helper), "create", *common, "--output", str(manifest)], check=True)
            document = json.loads(manifest.read_text(encoding="utf-8"))
            self.assertEqual(document["runner"], {"name": "codex", "version": "codex-cli 0.144.1"})
            self.assertEqual(set(document["suites"]), {"core", "validation", "held-out"})
            for suite in document["suites"].values():
                self.assertTrue(suite["tasks"])
                self.assertTrue(suite["fixtures"])
            subprocess.run([sys.executable, str(helper), "verify", *common, "--manifest", str(manifest)], check=True)

            incomplete_gate = self._passing_observed_gate(metadata["candidate_sha256"])
            del incomplete_gate["comparisons"]["held_out"]
            raw_gate.write_text(json.dumps(incomplete_gate), encoding="utf-8")
            incomplete = subprocess.run(
                [sys.executable, str(helper), "create", *common, "--output", str(manifest)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(incomplete.returncode, 0)
            bad_count = self._passing_observed_gate(metadata["candidate_sha256"])
            bad_count["comparisons"]["core"]["statistics"]["usable_pair_count"] = 5
            raw_gate.write_text(json.dumps(bad_count), encoding="utf-8")
            counted = subprocess.run(
                [sys.executable, str(helper), "create", *common, "--output", str(manifest)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(counted.returncode, 0)
            raw_gate.write_text(json.dumps(self._passing_observed_gate(metadata["candidate_sha256"])), encoding="utf-8")
            subprocess.run([sys.executable, str(helper), "create", *common, "--output", str(manifest)], check=True)

            for field, bad_value in (("runner_name", "unknown"), ("runner_version", "unknown"), ("runner_version", "codex-cli 0.144.0")):
                provenance_tampered = self._passing_observed_gate(metadata["candidate_sha256"])
                provenance_tampered[field] = bad_value
                raw_gate.write_text(json.dumps(provenance_tampered), encoding="utf-8")
                rejected = subprocess.run(
                    [sys.executable, str(helper), "create", *common, "--output", str(manifest)],
                    capture_output=True, text=True,
                )
                self.assertNotEqual(rejected.returncode, 0, (field, bad_value))
            raw_gate.write_text(json.dumps(self._passing_observed_gate(metadata["candidate_sha256"])), encoding="utf-8")
            subprocess.run([sys.executable, str(helper), "create", *common, "--output", str(manifest)], check=True)

            manifest_tampered = json.loads(manifest.read_text(encoding="utf-8"))
            manifest_tampered["runner"]["version"] = "codex-cli 0.144.0"
            manifest.write_text(json.dumps(manifest_tampered), encoding="utf-8")
            rejected_manifest = subprocess.run(
                [sys.executable, str(helper), "verify", *common, "--manifest", str(manifest)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(rejected_manifest.returncode, 0)
            subprocess.run([sys.executable, str(helper), "create", *common, "--output", str(manifest)], check=True)

            first_suite = document["suites"]["core"]
            first_fixture = next(iter(first_suite["fixtures"]))
            first_suite["fixtures"][first_fixture] = "0" * 64
            manifest.write_text(json.dumps(document), encoding="utf-8")
            suite_tampered = subprocess.run(
                [sys.executable, str(helper), "verify", *common, "--manifest", str(manifest)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(suite_tampered.returncode, 0)
            subprocess.run([sys.executable, str(helper), "create", *common, "--output", str(manifest)], check=True)

            (output / "candidate.SKILL.md").write_text(candidate_text + "tampered\n", encoding="utf-8")
            tampered = subprocess.run(
                [sys.executable, str(helper), "verify", *common, "--manifest", str(manifest)],
                capture_output=True, text=True,
            )
            self.assertNotEqual(tampered.returncode, 0)

    def test_single_real_host_orchestrator_builds_every_release_product(self) -> None:
        helper = REAL_AGENT / "run_real_host_gate.py"
        spec = importlib.util.spec_from_file_location("aet_real_host_gate", helper)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        calls = []
        release = None

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            if argv == ["git", "rev-parse", "HEAD"]:
                return subprocess.CompletedProcess(argv, 0, stdout="b" * 40 + "\n")
            candidate = Path(argv[argv.index("--candidate") + 1])
            metadata = json.loads((candidate / "candidate.json").read_text(encoding="utf-8"))
            raw_gate = Path(argv[argv.index("--output") + 1])
            raw_gate.write_text(json.dumps(self._passing_observed_gate(metadata["candidate_sha256"])), encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0)

        intent = json.loads((ROOT / "aet.intent.json").read_text(encoding="utf-8"))
        declared = next(proof for proof in intent["required_proofs"] if proof["id"] == "real-host-gate")["command"]
        declared_argv = shlex.split(declared)
        self.assertNotIn("$(", declared)
        self.assertNotIn("--commit", declared_argv)
        with tempfile.TemporaryDirectory() as temporary, mock.patch.object(module.subprocess, "run", fake_run), mock.patch.object(module, "__version__", "1.9.0"):
            release = Path(temporary) / "v1.9"
            replay_argv = declared_argv[2:]
            replay_argv[replay_argv.index("--root") + 1] = str(ROOT)
            replay_argv[replay_argv.index("--release-dir") + 1] = str(release)
            with mock.patch.object(sys, "argv", [str(helper), *replay_argv]):
                module.main()
            self.assertTrue((release / "candidate" / "candidate.SKILL.md").is_file())
            self.assertTrue((release / "raw-gate.json").is_file())
            self.assertTrue((release / "real-host-gate.json").is_file())
            runner = json.loads((release / "runner.json").read_text(encoding="utf-8"))
            self.assertEqual(runner, {"aet_argv": [sys.executable, "-m", "aet.cli"], "inherit_home": True})
            manifest = json.loads((release / "real-host-gate.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["runner"], {"name": "codex", "version": "codex-cli 0.144.1"})
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[0][0], ["git", "rev-parse", "HEAD"])
            argv, options = calls[1]
            self.assertEqual(argv[:3], [sys.executable, "-m", "aet.cli"])
            self.assertIn("--runner", argv)
            self.assertIn("codex", argv)
            self.assertIn("--rollouts", argv)
            self.assertIn("6", argv)
            self.assertEqual(options["cwd"], ROOT.resolve())
            self.assertTrue(options["check"])

    def test_release_suite_hashing_rejects_each_missing_empty_or_symlink_fixture(self) -> None:
        helper = REAL_AGENT / "release_gate.py"
        spec = importlib.util.spec_from_file_location("aet_release_gate", helper)
        self.assertIsNotNone(spec)
        self.assertIsNotNone(spec.loader)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            suite = root / "eval/real-agent/core"
            fixtures = root / "eval/real-agent/fixtures"
            suite.mkdir(parents=True)
            fixtures.mkdir(parents=True)
            task = suite / "task.json"
            task.write_text(json.dumps({"fixture": {"source": "../fixtures/case"}}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "existing non-symlink"):
                module.suite_hashes(root, "core")
            case = fixtures / "case"
            case.mkdir()
            with self.assertRaisesRegex(ValueError, "at least one regular file"):
                module.suite_hashes(root, "core")
            (case / "input.txt").write_text("fixture", encoding="utf-8")
            self.assertTrue(module.suite_hashes(root, "core")["fixtures"])
            task.unlink()
            target = suite / "target.json"
            target.write_text(json.dumps({"fixture": {"source": "../fixtures/case"}}), encoding="utf-8")
            task.symlink_to(target.name)
            with self.assertRaisesRegex(ValueError, "non-symlink"):
                module.suite_hashes(root, "core")

    def test_ci_release_and_install_example_have_required_delivery_gates(self) -> None:
        ci = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        for command in (
            "python -m pytest -q",
            "python -m pytest tests/test_business_quality_flows.py -q",
            "aet learn suite verify --suite eval/real-agent/core",
            "aet learn suite verify --suite eval/real-agent/validation",
            "aet learn suite verify --suite eval/real-agent/held-out",
            "aet learn suite verify --suite eval/real-agent/deterministic",
            "aet audit . --strict",
            "uv build",
            "wheel_version=",
            "source_version=",
            'test "$wheel_version" = "$source_version"',
        ):
            self.assertIn(command, ci)

        producer = (ROOT / ".github" / "workflows" / "real-host-gate.yml").read_text(encoding="utf-8")
        for binding in (
            "workflow_dispatch:", "commit:", "ref: ${{ inputs.commit }}", "EXPECTED_COMMIT: ${{ inputs.commit }}",
            '[[ "$EXPECTED_COMMIT" =~ ^[0-9a-f]{40}$ ]]', 'test "$(git rev-parse HEAD)" = "$EXPECTED_COMMIT"',
            'test "$(git rev-parse HEAD)" = "$GITHUB_SHA"',
            "@openai/codex@0.144.1", "codex-cli 0.144.1", "eval/real-agent/run_real_host_gate.py",
            ".aet/release/v1.9/raw-gate.json", ".aet/release/v1.9/real-host-gate.json",
            "name: real-host-gate",
        ):
            self.assertIn(binding, producer)
        self.assertNotIn('test "$(git rev-parse HEAD)" = "${{ inputs.commit }}"', producer)

        release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        for binding in (
            "workflow_dispatch:", "gate_run_id:", "actions/download-artifact@v4", "real-host-gate",
            "gh api", "head_sha", ".github/workflows/real-host-gate.yml", "GITHUB_SHA",
            "eval/real-agent/build_candidate.py", "eval/real-agent/release_gate.py verify",
            ".aet/release/v1.9/raw-gate.json", ".aet/release/v1.9/real-host-gate.json",
            "wheel_version=", "source_version=", 'test "$wheel_version" = "$source_version"',
            '[[ "$RELEASE_TAG" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$ ]]',
            'git show-ref --verify "refs/tags/$RELEASE_TAG"',
        ):
            self.assertIn(binding, release)
        self.assertNotIn('run: gh release create "${{ inputs.tag }}"', release)

        intent = json.loads((ROOT / "aet.intent.json").read_text(encoding="utf-8"))
        business_proof = next(proof for proof in intent["required_proofs"] if proof["id"] == "business-flow")
        self.assertIn("tests/test_business_quality_flows.py", business_proof["command"])
        real_host = next(proof for proof in intent["required_proofs"] if proof["id"] == "real-host-gate")
        self.assertIn("eval/real-agent/run_real_host_gate.py", real_host["command"])
        self.assertIn("--release-dir .aet/release/v1.9", real_host["command"])
        self.assertNotIn("$(", real_host["command"])
        self.assertEqual(
            real_host["evidence"],
            [".aet/release/v1.9/real-host-gate.json", ".aet/release/v1.9/raw-gate.json"],
        )

        example = (ROOT / "examples" / "github-actions" / "aet-audit.yml").read_text(encoding="utf-8")
        self.assertIn("actions/checkout@v4", example)
        self.assertRegex(example, r"uv (?:tool install|run).*\.")
        self.assertNotIn("uv tool install agent-engineering-toolkit", example)


if __name__ == "__main__":
    unittest.main()
