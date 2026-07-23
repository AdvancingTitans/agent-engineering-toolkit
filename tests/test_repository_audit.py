from __future__ import annotations

import json
import subprocess
import time
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from aet.cli import main
from aet import repository_audit
from aet.repository_audit import RepositoryAuditError, run_repository_audit


class RepositoryAuditTests(unittest.TestCase):
    def test_case_writes_exact_evidence_backed_bundle_without_source_text(self) -> None:
        with _fixture() as (root, profile):
            output = root.parent / "audit-result"
            with patch("aet.repository_audit._find_profile", return_value=profile):
                result = run_repository_audit("swe-agent", root, output)
            self.assertEqual(
                {path.relative_to(output).as_posix() for path in output.rglob("*") if path.is_file()},
                {
                    "evidence_manifest.json",
                    "findings.json",
                    "en/repository-summary.md",
                    "en/audit-report.md",
                    "en/audit-report.html",
                    "en/diagrams/agent-flow.svg",
                    "en/diagrams/evidence-chain.svg",
                    "zh-CN/repository-summary.md",
                    "zh-CN/audit-report.md",
                    "zh-CN/audit-report.html",
                    "zh-CN/diagrams/agent-flow.svg",
                    "zh-CN/diagrams/evidence-chain.svg",
                },
            )
            self.assertEqual(result["schema_version"], "repository-audit-result/v1")
            self.assertEqual(result["summary"]["FAIL"], 0)
            self.assertTrue(all(finding["evidence"] for finding in result["findings"]))
            manifest = json.loads((output / "evidence_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], "repository-evidence-manifest/v1")
            self.assertEqual(manifest["profile"]["case_id"], "swe-agent")
            self.assertNotIn(str(profile.parent), json.dumps(manifest))
            rendered = "\n".join(path.read_text(encoding="utf-8") for path in output.rglob("*") if path.is_file())
            self.assertNotIn("PRIVATE-SOURCE-SENTINEL", rendered)
            chinese = (output / "zh-CN" / "audit-report.md").read_text(encoding="utf-8")
            self.assertIn("工程观察", chinese)
            self.assertIn("验证证据可核查", chinese)
            self.assertIn("- 建议：", chinese)
            chinese_html = (output / "zh-CN" / "audit-report.html").read_text(encoding="utf-8")
            self.assertIn('lang="zh-CN"', chinese_html)
            self.assertIn("overflow-wrap:anywhere", chinese_html)
            self.assertIn("严重程度：", chinese_html)
            self.assertIn("影响级别：", chinese_html)
            self.assertIn("category=verification; sha256=", chinese_html)
            self.assertIn(
                "若检出版本不匹配或工作树不干净，行级证据将无法复现。",
                chinese_html,
            )

    def test_cli_alias_requires_repo_and_preserves_legacy_path_mode(self) -> None:
        with self.assertRaisesRegex(SystemExit, "requires --repo"):
            main(["audit", "swe-agent"])
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("# Instructions\n", encoding="utf-8")
            output = root / "audit.json"
            self.assertEqual(main(["audit", str(root), "--format", "json", "--output", str(output)]), 0)
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["report_kind"], "audit")

    def test_cli_case_generates_bundle_and_strict_rejects_unknown(self) -> None:
        with _fixture(include_verification=False) as (root, profile):
            output = root.parent / "bundle"
            with patch("aet.repository_audit._find_profile", return_value=profile):
                self.assertEqual(main(["audit", "swe-agent", "--repo", str(root), "--output-dir", str(output)]), 0)
                self.assertEqual(
                    main(["audit", "swe-agent", "--repo", str(root), "--output-dir", str(output), "--strict"]),
                    1,
                )
            findings = json.loads((output / "findings.json").read_text(encoding="utf-8"))
            objective = next(item for item in findings["findings"] if item["id"] == "AET-REPO-003")
            self.assertEqual(objective["status"], "UNKNOWN")
            self.assertIn("verification", objective["impact"]["description"])

    def test_mismatched_or_dirty_checkout_fails_reproducibility(self) -> None:
        with _fixture() as (root, profile):
            document = json.loads(profile.read_text(encoding="utf-8"))
            document["repository"]["commit"] = "0" * 40
            profile.write_text(json.dumps(document), encoding="utf-8")
            with patch("aet.repository_audit._find_profile", return_value=profile):
                result = run_repository_audit("swe-agent", root, root.parent / "output")
            lock = next(item for item in result["findings"] if item["id"] == "AET-REPO-001")
            self.assertEqual(lock["status"], "FAIL")

    def test_openhands_profile_cannot_drop_enterprise_prohibition(self) -> None:
        with _fixture(case_id="openhands") as (root, profile):
            document = json.loads(profile.read_text(encoding="utf-8"))
            document["scope"]["prohibited"] = []
            profile.write_text(json.dumps(document), encoding="utf-8")
            with patch("aet.repository_audit._find_profile", return_value=profile):
                with self.assertRaisesRegex(RepositoryAuditError, "must prohibit enterprise"):
                    run_repository_audit("openhands", root, root.parent / "output")

    def test_scope_cannot_follow_a_directory_symlink_outside_repository(self) -> None:
        with _fixture() as (root, profile):
            outside = root.parent / "outside"
            outside.mkdir()
            (outside / "secret.py").write_text("PRIVATE-OUTSIDE-SOURCE\n", encoding="utf-8")
            (root / "linked").symlink_to(outside, target_is_directory=True)
            document = json.loads(profile.read_text(encoding="utf-8"))
            document["scope"]["include"].append("linked/**")
            profile.write_text(json.dumps(document), encoding="utf-8")
            output = root.parent / "output"
            with patch("aet.repository_audit._find_profile", return_value=profile):
                run_repository_audit("swe-agent", root, output)
            rendered = (output / "evidence_manifest.json").read_text(encoding="utf-8")
            self.assertNotIn("secret.py", rendered)
            self.assertNotIn("PRIVATE-OUTSIDE-SOURCE", rendered)

    def test_profile_paths_and_output_cannot_escape_safety_boundaries(self) -> None:
        with _fixture() as (root, profile):
            document = json.loads(profile.read_text(encoding="utf-8"))
            document["scope"]["include"] = ["../outside/**"]
            profile.write_text(json.dumps(document), encoding="utf-8")
            with patch("aet.repository_audit._find_profile", return_value=profile):
                with self.assertRaisesRegex(RepositoryAuditError, "cannot escape"):
                    run_repository_audit("swe-agent", root, root.parent / "output")
            document["scope"]["include"] = ["src/**"]
            profile.write_text(json.dumps(document), encoding="utf-8")
            with patch("aet.repository_audit._find_profile", return_value=profile):
                with self.assertRaisesRegex(RepositoryAuditError, "outside the audited repository"):
                    run_repository_audit("swe-agent", root, root / "audit-result")

    def test_profiles_and_schemas_are_machine_readable(self) -> None:
        project = Path(__file__).resolve().parents[1]
        for case_id in ("swe-agent", "google-adk", "openhands"):
            profile = json.loads(
                (project / "repository-audit-showcase" / "profiles" / f"{case_id}.json").read_text(encoding="utf-8")
            )
            self.assertEqual(profile["schema_version"], "repository-audit-profile/v1")
            self.assertEqual(profile["case_id"], case_id)
        for path in (
            project / "repository-audit-showcase" / "schemas" / "repository-audit-profile-v1.schema.json",
            project / "repository-audit-showcase" / "schemas" / "repository-audit-result-v1.schema.json",
            project / "repository-audit-showcase" / "schemas" / "repository-evidence-manifest-v1.schema.json",
        ):
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["$schema"], "https://json-schema.org/draft/2020-12/schema")

    def test_comments_empty_files_and_license_words_are_not_control_evidence(self) -> None:
        empty = repository_audit._categorize("src/agents/__init__.py", "")
        license_header = repository_audit._categorize(
            "src/agents/__init__.py",
            "# Licensed under terms governing permissions and limitations.\n",
        )
        unrelated = repository_audit._categorize(
            "src/module.py",
            "message = 'permission recovery feedback sandbox'\n",
        )
        self.assertEqual(empty, {})
        self.assertNotIn("permission", license_header)
        self.assertNotIn("local_agent_definition", license_header)
        self.assertFalse({"permission", "recovery", "feedback", "isolation"} & set(unrelated))

    def test_profile_runtime_contract_is_validated_without_key_errors(self) -> None:
        with _fixture() as (root, profile):
            document = json.loads(profile.read_text(encoding="utf-8"))
            document["runtime"] = {"max_seconds": 900}
            profile.write_text(json.dumps(document), encoding="utf-8")
            with patch("aet.repository_audit._find_profile", return_value=profile):
                with self.assertRaisesRegex(RepositoryAuditError, "runtime"):
                    run_repository_audit("swe-agent", root, root.parent / "output")

    def test_bundle_replacement_removes_stale_files_and_times_rendering(self) -> None:
        with _fixture() as (root, profile):
            output = root.parent / "output"
            output.mkdir()
            (output / "stale.txt").write_text("stale\n", encoding="utf-8")
            original_render = repository_audit._render_bundle

            def delayed_render(*args: object, **kwargs: object) -> dict[str, str]:
                time.sleep(0.03)
                return original_render(*args, **kwargs)

            with (
                patch("aet.repository_audit._find_profile", return_value=profile),
                patch("aet.repository_audit._render_bundle", side_effect=delayed_render),
            ):
                result = run_repository_audit("swe-agent", root, output)
            self.assertFalse((output / "stale.txt").exists())
            self.assertGreaterEqual(result["runtime"]["total_seconds"], 0.03)

    def test_legacy_audit_rejects_repository_only_output_option(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "AGENTS.md").write_text("# Instructions\n", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "only valid"):
                main(["audit", str(root), "--output-dir", str(root / "bundle")])


class _fixture:
    def __init__(self, *, include_verification: bool = True, case_id: str = "swe-agent") -> None:
        self.temporary = TemporaryDirectory()
        self.include_verification = include_verification
        self.case_id = case_id

    def __enter__(self) -> tuple[Path, Path]:
        parent = Path(self.temporary.name)
        root = parent / "repo"
        root.mkdir()
        _git(root, "init", "-q")
        _git(root, "config", "user.email", "aet@example.invalid")
        _git(root, "config", "user.name", "AET Test")
        (root / "LICENSE").write_text("MIT fixture\n", encoding="utf-8")
        agent = root / "src" / "agent"
        agent.mkdir(parents=True)
        (agent / "loop.py").write_text(
            "class DemoAgent:\n"
            "    def run_tool(self):\n"
            "        try:\n"
            "            return 'PRIVATE-SOURCE-SENTINEL'\n"
            "        except RuntimeError:\n"
            "            return 'failure'\n",
            encoding="utf-8",
        )
        if self.include_verification:
            tests = root / "tests"
            tests.mkdir()
            (tests / "test_agent.py").write_text("def test_agent():\n    assert True\n", encoding="utf-8")
        _git(root, "add", "LICENSE", "src", *(["tests"] if self.include_verification else []))
        _git(root, "commit", "-qm", "fixture")
        commit = _git(root, "rev-parse", "HEAD")
        license_blob = _git(root, "hash-object", "LICENSE")
        profile = parent / "profile.json"
        profile.write_text(
            json.dumps(
                {
                    "schema_version": "repository-audit-profile/v1",
                    "case_id": self.case_id,
                    "repository": {
                        "name": "Fixture",
                        "url": "https://github.com/example/fixture",
                        "branch": "main",
                        "commit": commit,
                        "license": {"spdx": "MIT", "path": "LICENSE", "blob_sha": license_blob},
                    },
                    "scope": {
                        "include": ["src/**", "tests/**"],
                        "exclude": ["docs/**"],
                        "prohibited": ["enterprise/**"] if self.case_id == "openhands" else ["vendor/**"],
                        "extensions": [".py"],
                        "max_file_bytes": 100000,
                    },
                    "objectives": [
                        {
                            "title": "Verification evidence is present",
                            "required_categories": ["agent", "verification"],
                            "pass_claim": "Agent and verification evidence are both present.",
                            "unknown_claim": "The static scope does not prove the verification link.",
                            "impact": {"level": "medium"},
                            "recommendation": "Add an explicit verification evidence checkpoint.",
                            "localization": {
                                "zh-CN": {
                                    "title": "验证证据可核查",
                                    "pass_claim": "Agent 与验证证据均已存在。",
                                    "unknown_claim": "静态范围不足以证明验证关联。",
                                    "recommendation": "增加明确的验证证据检查点。"
                                }
                            },
                        }
                    ],
                    "flow": {
                        "nodes": [
                            {"label": "Agent", "label_zh_cn": "Agent", "category": "agent"},
                            {"label": "Tool", "label_zh_cn": "工具", "category": "tool"},
                            {"label": "Verification", "label_zh_cn": "验证", "category": "verification"},
                        ]
                    },
                    "runtime": {
                        "max_seconds": 900,
                        "starts_when": "local_repository_exists_and_dependencies_are_installed",
                        "includes": [
                            "evidence_collection",
                            "rule_analysis",
                            "artifact_generation",
                            "html_svg_rendering",
                        ],
                        "excludes": [
                            "clone",
                            "dependency_install",
                            "llm_network",
                            "manual_review",
                        ],
                    },
                }
            ),
            encoding="utf-8",
        )
        return root, profile

    def __exit__(self, *args: object) -> None:
        self.temporary.cleanup()


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(["git", *args], cwd=root, text=True, capture_output=True, check=True)
    return completed.stdout.strip()


if __name__ == "__main__":
    unittest.main()
