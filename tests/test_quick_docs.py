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

    def test_bilingual_architecture_and_intro_media_are_real_files(self) -> None:
        assets = ROOT / "docs" / "assets"
        for locale in ("en", "zh-CN"):
            svg = assets / f"aet-quick-architecture-{locale}.svg"
            png = assets / f"aet-quick-architecture-{locale}.png"
            video = assets / f"aet-quick-intro-{locale}.webm"
            self.assertIn("AET Quick", svg.read_text(encoding="utf-8"))
            with png.open("rb") as stream:
                self.assertEqual(stream.read(8), b"\x89PNG\r\n\x1a\n")
                length = struct.unpack(">I", stream.read(4))[0]
                self.assertEqual(stream.read(4), b"IHDR")
                width, height = struct.unpack(">II", stream.read(8))
                self.assertEqual((width, height), (1600, 900))
                self.assertEqual(length, 13)
            self.assertGreater(video.stat().st_size, 100_000)
            self.assertEqual(video.read_bytes()[:4], b"\x1aE\xdf\xa3")

    def test_video_manifest_binds_decoded_media_properties(self) -> None:
        assets = ROOT / "docs" / "assets"
        manifest = json.loads(
            (assets / "aet-quick-media-manifest.json").read_text(encoding="utf-8")
        )
        self.assertEqual(manifest["schema_version"], "aet-quick-media-manifest/v1")
        videos = [item for item in manifest["assets"] if item["kind"] == "video"]
        diagrams = [item for item in manifest["assets"] if item["kind"] == "architecture"]
        self.assertEqual({item["language"] for item in videos}, {"en", "zh-CN"})
        self.assertEqual(
            {(item["language"], item["format"]) for item in diagrams},
            {("en", "png"), ("en", "svg"), ("zh-CN", "png"), ("zh-CN", "svg")},
        )
        hashes = set()
        for item in manifest["assets"]:
            video = assets / item["path"]
            digest = hashlib.sha256(video.read_bytes()).hexdigest()
            self.assertEqual(digest, item["sha256"])
            hashes.add(digest)
        for item in videos:
            self.assertEqual(item["codec"], "vp9")
            self.assertEqual((item["width"], item["height"]), (1280, 720))
            self.assertEqual(item["frames"], 270)
            self.assertEqual(item["frame_rate"], "30/1")
            self.assertEqual(item["duration_seconds"], 9.0)
        self.assertEqual(len(hashes), 6, "all bilingual media must be byte-distinct")


if __name__ == "__main__":
    unittest.main()
