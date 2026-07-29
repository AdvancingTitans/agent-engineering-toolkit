from __future__ import annotations

import hashlib
import json
import re
import struct
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class QuickDocumentationTests(unittest.TestCase):
    def test_five_quick_schemas_are_packaged_contracts(self) -> None:
        names = (
            "intent-v2.schema.json",
            "investigation-ledger-v1.schema.json",
            "investigation-contract-v1.schema.json",
            "investigated-finding-v1.schema.json",
            "command-budget-v1.schema.json",
            "proof-receipt-v2.schema.json",
        )
        for name in names:
            with self.subTest(name=name):
                data = json.loads((ROOT / "schemas" / name).read_text(encoding="utf-8"))
                self.assertEqual(data["$schema"], "https://json-schema.org/draft/2020-12/schema")
                self.assertIn("schema_version", data["properties"])

    def test_four_quick_skills_have_boundary_budget_language_and_stop_rules(self) -> None:
        for name in ("aet-check", "aet-scope", "aet-proof", "aet-fresh"):
            with self.subTest(name=name):
                text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
                self.assertIn(f"name: {name}", text)
                self.assertIn("stop", text.lower())
                self.assertIn("Chinese", text)
                self.assertRegex(text, r"Otherwise\s+use English")
                self.assertRegex(text, r"Budget:|three seconds|command duration")
                self.assertNotIn("auto-adopt", text.lower())

    def test_readmes_put_quick_before_showcase_and_keep_fact_parity(self) -> None:
        english = (ROOT / "README.md").read_text(encoding="utf-8")
        chinese = (ROOT / "docs" / "README.zh-CN.md").read_text(encoding="utf-8")
        for token in ("/aet-check", "/aet-scope", "/aet-proof", "/aet-fresh"):
            self.assertIn(token, english)
            self.assertIn(token, chinese)
        self.assertLess(english.index("## Four Quick Skills"), english.index("## Real-world Repository Audit Showcase"))
        self.assertLess(chinese.index("## 四个 Quick Skill"), chinese.index("## 真实仓库审查案例库"))
        for state in (
            "EXACT_MATCH",
            "RELEVANT_FILES_MATCH",
            "HEAD_CHANGED_RELEVANT_FILES_MATCH",
            "RELEVANT_FILES_CHANGED",
            "ARTIFACT_CHANGED",
            "ENVIRONMENT_CHANGED",
            "UNKNOWN",
        ):
            self.assertIn(state, english)
            self.assertIn(state, chinese)

    def test_readme_local_links_exist(self) -> None:
        for readme in (ROOT / "README.md", ROOT / "docs" / "README.zh-CN.md"):
            text = readme.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                if "://" in target or target.startswith("#"):
                    continue
                path = target.split("#", 1)[0]
                with self.subTest(readme=readme.name, target=target):
                    self.assertTrue((readme.parent / path).exists())

    def test_bilingual_workflow_panorama_and_intro_media_are_real_files(self) -> None:
        assets = ROOT / "docs" / "assets"
        expected_workflow_titles = {
            "en": "Evidence-to-Improvement Review",
            "zh-CN": "从证据到代码改进",
        }
        for locale in ("en", "zh-CN"):
            workflow_svg = assets / f"aet-quick-workflow-{locale}.svg"
            workflow_gif = assets / f"aet-quick-workflow-{locale}.gif"
            panorama_svg = assets / f"aet-project-panorama-{locale}.svg"
            panorama_png = assets / f"aet-project-panorama-{locale}.png"
            video = assets / f"aet-product-intro-{locale}.mp4"
            motion = json.loads(
                (assets / f"aet-quick-workflow-{locale}.motion.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertIn(
                expected_workflow_titles[locale],
                workflow_svg.read_text(encoding="utf-8"),
            )
            self.assertEqual(workflow_gif.read_bytes()[:6], b"GIF89a")
            self.assertTrue(motion["ok"])
            self.assertEqual(motion["source_checks"]["composition"]["ok"], True)
            self.assertIn(
                "AET",
                panorama_svg.read_text(encoding="utf-8"),
            )
            with panorama_png.open("rb") as stream:
                self.assertEqual(stream.read(8), b"\x89PNG\r\n\x1a\n")
                length = struct.unpack(">I", stream.read(4))[0]
                self.assertEqual(stream.read(4), b"IHDR")
                width, height = struct.unpack(">II", stream.read(8))
                self.assertEqual((width, height), (1600, 1000))
                self.assertEqual(length, 13)
            self.assertGreater(video.stat().st_size, 1_000_000)
            self.assertEqual(video.read_bytes()[4:8], b"ftyp")
            self.assertNotIn(".webm", video.name)

    def test_media_manifest_binds_generated_media_properties(self) -> None:
        assets = ROOT / "docs" / "assets"
        manifest = json.loads(
            (assets / "aet-quick-media-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema_version"], "aet-quick-media-manifest/v2")
        videos = [item for item in manifest["assets"] if item["kind"] == "product_video"]
        animations = [
            item for item in manifest["assets"] if item["kind"] == "workflow_animation"
        ]
        panoramas = [
            item for item in manifest["assets"] if item["kind"] == "project_panorama"
        ]
        self.assertEqual({item["language"] for item in videos}, {"en", "zh-CN"})
        self.assertEqual({item["language"] for item in animations}, {"en", "zh-CN"})
        self.assertEqual(
            {(item["language"], item["format"]) for item in panoramas},
            {("en", "png"), ("en", "svg"), ("zh-CN", "png"), ("zh-CN", "svg")},
        )
        hashes = set()
        for item in manifest["assets"]:
            artifact = assets / item["path"]
            digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
            self.assertEqual(digest, item["sha256"])
            hashes.add(digest)
        for item in animations:
            self.assertEqual(item["codec"], "gif")
            self.assertEqual((item["width"], item["height"]), (960, 700))
            self.assertEqual(item["frames"], 115)
            self.assertEqual(item["frame_rate"], "20/1")
            self.assertEqual(item["duration_seconds"], 5.75)
            report = json.loads((assets / item["motion_report"]).read_text(encoding="utf-8"))
            self.assertTrue(report["ok"])
            self.assertEqual(report["artifact"]["sha256"], item["sha256"])
        for item in videos:
            self.assertEqual(item["video_codec"], "h264")
            self.assertIsNone(item["audio_codec"])
            self.assertEqual((item["width"], item["height"]), (1600, 900))
            self.assertEqual(item["frames"], 900)
            self.assertEqual(item["frame_rate"], "30/1")
            self.assertEqual(item["duration_seconds"], 30.0)
        self.assertEqual(len(hashes), 10, "all bilingual media must be byte-distinct")

    def test_improvement_case_media_is_bilingual_and_content_addressed(self) -> None:
        assets = ROOT / "docs" / "assets"
        manifest = json.loads(
            (assets / "aet-improvement-media-manifest.json").read_text(
                encoding="utf-8"
            )
        )
        self.assertEqual(manifest["release"], "v1.16.0")
        self.assertEqual(manifest["example"]["issue_id"], "IMP-001")
        self.assertEqual(manifest["motion"]["frames"], 6)
        self.assertEqual(len(manifest["media"]), 6)
        for item in manifest["media"]:
            artifact = ROOT / item["path"]
            self.assertEqual(artifact.stat().st_size, item["bytes"])
            self.assertEqual(
                hashlib.sha256(artifact.read_bytes()).hexdigest(),
                item["sha256"],
            )


if __name__ == "__main__":
    unittest.main()
