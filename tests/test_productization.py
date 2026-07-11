from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from aet.cli import main
from aet.discovery import discover_assets
from aet.evolve import build_evolution, collect_evolution, write_evolution_report
from aet.rules import run_rules


class ProductizationTests(unittest.TestCase):
    def test_audit_config_excludes_fixture_with_a_visible_reason(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("# Instructions\n", encoding="utf-8")
            broken = root / "tests" / "fixtures" / "broken"
            broken.mkdir(parents=True)
            (broken / "AGENTS.md").write_text("[missing](missing.md)\n", encoding="utf-8")
            (root / "aet.toml").write_text(
                "[scan]\nexclude = [{ pattern = 'tests/fixtures/**', reason = 'negative fixtures' }]\n",
                encoding="utf-8",
            )
            output = root / "audit.json"
            self.assertEqual(main(["audit", str(root), "--format", "json", "--output", str(output), "--strict"]), 0)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["FAIL"], 0)
            self.assertEqual(report["scope"]["config"]["exclusions"][0]["reason"], "negative fixtures")

    def test_audit_reports_missing_absolute_local_instruction_path(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            missing = root / "not-here" / "SKILL.md"
            (root / "AGENTS.md").write_text(f"Read {missing} before work.\n", encoding="utf-8")
            findings = run_rules(root, discover_assets(root))
            self.assertIn("AET-CTX-003", {finding.rule_id for finding in findings})

    def test_audit_config_include_limits_audit_to_the_declared_asset_boundary(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("# Current instructions\n", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "AGENTS.md").write_text("[missing](missing.md)\n", encoding="utf-8")
            (root / "aet.toml").write_text("[scan]\ninclude = ['AGENTS.md']\nexclude = []\n", encoding="utf-8")
            output = root / "audit.json"
            self.assertEqual(main(["audit", str(root), "--format", "json", "--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["assets"], [{"path": "AGENTS.md", "kind": "instruction"}])

    def test_trace_proof_binding_is_checked_in_evidence_pack(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "aet.intent.json").write_text(json.dumps({
                "intent": "Verify a proof binding.",
                "changed_path_budget": 1,
                "allowed_paths": ["aet.intent.json"],
                "required_proofs": [{"id": "unit", "command": "python -c pass", "evidence": ["aet.intent.json"]}],
            }), encoding="utf-8")
            audit = root / "audit.json"
            review = root / "review.json"
            trace = root / "trace.json"
            pack = root / "pack.json"
            self.assertEqual(main(["audit", str(root), "--format", "json", "--output", str(audit)]), 0)
            _write_review_report(review, root, (root / "aet.intent.json").read_bytes(), "unit")
            self.assertEqual(main(["trace", "--proof", "unit", "--intent", str(root / "aet.intent.json"), "--output", str(trace), "--", "python3", "-c", "pass"]), 0)
            self.assertEqual(main(["evidence", "pack", "--audit", str(audit), "--review", str(review), "--trace", str(trace), "--output", str(pack)]), 0)
            data = json.loads(pack.read_text(encoding="utf-8"))
            self.assertEqual(data["proof_binding"]["status"], "PASS")

    def test_run_manifest_records_a_complete_evidence_only_lifecycle(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _git(root, "init")
            _git(root, "config", "user.email", "aet@example.test")
            _git(root, "config", "user.name", "AET test")
            (root / "README.md").write_text("base\n", encoding="utf-8")
            (root / ".gitignore").write_text(".aet/\n", encoding="utf-8")
            _git(root, "add", "README.md", ".gitignore")
            _git(root, "commit", "-m", "base")
            base = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
            intent = root / "aet.intent.json"
            intent.write_text(json.dumps({
                "intent": "Verify a complete run.", "changed_path_budget": 1,
                "allowed_paths": ["aet.intent.json"],
                "required_proofs": [{"id": "unit", "command": "python -c pass", "evidence": ["aet.intent.json"]}],
            }), encoding="utf-8")
            run = root / ".aet" / "runs" / "release.json"
            audit, review, trace, pack = (root / ".aet" / "evidence" / name for name in ("audit.json", "review.json", "trace.json", "pack.json"))
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["run", "init", "--intent", "aet.intent.json", "--output", str(run)]), 0)
                self.assertEqual(main(["audit", ".", "--format", "json", "--output", str(audit), "--run", str(run)]), 0)
                self.assertEqual(main(["review", ".", "--base", base, "--format", "json", "--output", str(review), "--run", str(run)]), 0)
                self.assertEqual(main(["trace", "--proof", "unit", "--intent", "aet.intent.json", "--output", str(trace), "--run", str(run), "--", "python3", "-c", "pass"]), 0)
                self.assertEqual(main(["evidence", "pack", "--audit", str(audit), "--review", str(review), "--trace", str(trace), "--output", str(pack), "--run", str(run)]), 0)
                self.assertEqual(main(["run", "close", "--run", str(run), "--format", "json"]), 0)
            finally:
                os.chdir(previous)
            manifest = json.loads(run.read_text(encoding="utf-8"))
            self.assertEqual(manifest["lifecycle"]["state"], "CLOSED")
            self.assertEqual([event["event"] for event in manifest["lifecycle"]["history"]], ["created", "bind_intent", "attach_audit", "attach_review", "attach_trace", "attach_evidence_pack", "close"])

    def test_run_verify_persists_stale_after_the_workspace_changes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _git(root, "init")
            _git(root, "config", "user.email", "aet@example.test")
            _git(root, "config", "user.name", "AET test")
            (root / "README.md").write_text("base\n", encoding="utf-8")
            (root / ".gitignore").write_text(".aet/\n", encoding="utf-8")
            _git(root, "add", "README.md", ".gitignore")
            _git(root, "commit", "-m", "base")
            (root / "aet.intent.json").write_text(json.dumps({
                "intent": "Verify stale state.", "changed_path_budget": 1,
                "allowed_paths": ["aet.intent.json"],
                "required_proofs": [{"id": "unit", "command": "python -c pass", "evidence": ["aet.intent.json"]}],
            }), encoding="utf-8")
            run = root / ".aet" / "runs" / "run.json"
            audit = root / ".aet" / "evidence" / "audit.json"
            previous = Path.cwd()
            try:
                os.chdir(root)
                self.assertEqual(main(["run", "init", "--output", str(run)]), 0)
                self.assertEqual(main(["audit", ".", "--format", "json", "--output", str(audit), "--run", str(run)]), 0)
                (root / "README.md").write_text("changed\n", encoding="utf-8")
                self.assertEqual(main(["run", "verify", "--run", str(run), "--format", "json"]), 1)
            finally:
                os.chdir(previous)
            manifest = json.loads(run.read_text(encoding="utf-8"))
            self.assertEqual(manifest["lifecycle"]["state"], "STALE")
            self.assertEqual(manifest["lifecycle"]["history"][-1]["event"], "repository_changed")

    def test_init_never_overwrites_existing_candidate(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "aet.toml"
            self.assertEqual(main(["init", "--output", str(output)]), 0)
            self.assertIn("[scan]", output.read_text(encoding="utf-8"))
            with self.assertRaises(SystemExit):
                main(["init", "--output", str(output)])

    def test_evolve_builds_reproducible_local_history_with_direct_and_candidate_links(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _git(root, "init")
            _git(root, "config", "user.email", "aet@example.test")
            _git(root, "config", "user.name", "AET test")
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            _git(root, "add", "README.md")
            _git(root, "commit", "-m", "initial architecture")
            (root / "README.md").write_text("# Demo\n\nRelease v1.0.0\n", encoding="utf-8")
            _git(root, "add", "README.md")
            _git(root, "commit", "-m", "release preparation #42")
            _git(root, "tag", "v1.0.0")
            output = root / ".aet" / "evolve" / "case"
            manifest = collect_evolution(root, output, question="Why was v1.0.0 released?")
            graph = build_evolution(manifest, output)
            report = write_evolution_report(graph, output)
            links = json.loads((output / "linkage-report.json").read_text(encoding="utf-8"))["links"]
            self.assertTrue(any(link["confidence"] == "DIRECT" for link in links))
            self.assertTrue(any(link["confidence"] == "CANDIDATE" for link in links))
            self.assertIn("DIRECT", report.read_text(encoding="utf-8"))
            self.assertEqual(json.loads((output / "evolution-pack.json").read_text(encoding="utf-8"))["report_kind"], "evolution")

    def test_evolve_links_github_export_issue_pr_and_release_to_local_git_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            _git(root, "init")
            _git(root, "config", "user.email", "aet@example.test")
            _git(root, "config", "user.name", "AET test")
            (root / "README.md").write_text("# Demo\n", encoding="utf-8")
            _git(root, "add", "README.md")
            _git(root, "commit", "-m", "fixes #9")
            sha = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, text=True, capture_output=True, check=True).stdout.strip()
            _git(root, "tag", "v1.0.0")
            export = root / "github.json"
            export.write_text(json.dumps({
                "issues": [{"number": 9, "title": "tracked issue"}],
                "pull_requests": [{"number": 10, "head": {"sha": sha}}],
                "releases": [{"tag_name": "v1.0.0", "name": "Release"}],
            }), encoding="utf-8")
            output = root / "out"
            manifest = collect_evolution(root, output, question="What shipped?", source_export=export)
            build_evolution(manifest, output)
            links = json.loads((output / "linkage-report.json").read_text(encoding="utf-8"))["links"]
            pairs = {(link["from"], link["to"], link["confidence"]) for link in links}
            self.assertIn((f"commit:{sha}", "issue:9", "DIRECT"), pairs)
            self.assertIn(("pull_request:10", f"commit:{sha}", "DIRECT"), pairs)
            self.assertIn(("release:v1.0.0", "tag:v1.0.0", "DIRECT"), pairs)

    def test_evidence_viewer_is_derived_from_pack_without_external_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pack = root / "pack.json"
            pack.write_text(json.dumps({"report_kind": "evidence_pack", "schema_version": "1.0.0", "components": {}}), encoding="utf-8")
            viewer = root / "viewer.html"
            self.assertEqual(main(["evidence", "viewer", "--pack", str(pack), "--output", str(viewer)]), 0)
            html = viewer.read_text(encoding="utf-8")
            self.assertIn("Evidence Pack", html)
            self.assertIn("Snapshot binding", html)
            self.assertIn("INCOMPLETE", html)
            self.assertNotIn("<script src=", html)

    def test_triage_score_is_explainable_and_cannot_change_finding_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = root / "audit.json"
            report.write_text(json.dumps({
                "report_kind": "audit", "findings": [{
                    "rule_id": "AET-X", "status": "FAIL", "severity": "ERROR", "claim": "missing proof",
                    "evidence": [{"path": "AGENTS.md", "line": 4, "detail": "proof.py"}], "remediation": "restore it",
                }],
            }), encoding="utf-8")
            output = root / "triage.json"
            self.assertEqual(main(["triage", "--report", str(report), "--output", str(output)]), 0)
            item = json.loads(output.read_text(encoding="utf-8"))["items"][0]
            self.assertEqual(item["status"], "FAIL")
            self.assertEqual(item["factors"]["severity"], 40)
            self.assertIn("model_version", item)


def _write_review_report(path: Path, root: Path, contract_bytes: bytes, proof_id: str) -> None:
    import hashlib

    path.write_text(json.dumps({
        "schema_version": "1.0.0",
        "report_kind": "review",
        "generated_at": "2026-07-11T00:00:00+00:00",
        "root": str(root),
        "scope": {"root": str(root)},
        "assets": [],
        "claims": [],
        "sources": [],
        "findings": [],
        "summary": {"PASS": 1, "FAIL": 0, "UNKNOWN": 0, "NOT_APPLICABLE": 0},
        "review": {"contract_sha256": hashlib.sha256(contract_bytes).hexdigest(), "proofs": [{"id": proof_id, "command": "python -c pass"}]},
    }), encoding="utf-8")


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=root, check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
