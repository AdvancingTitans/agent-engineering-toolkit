import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from aet.demo.errors import DemoInvariantError, DemoUnavailable
from aet.demo.registry import get_demo
from aet.demo.sandbox import create_sandbox, resolve_workspace_path


class DemoSandboxTests(unittest.TestCase):
    def test_creates_git_workspace_and_cleans_by_default(self) -> None:
        manifest = get_demo("stale-proof")
        with create_sandbox(manifest) as box:
            root = box.root
            self.assertTrue((box.workspace / ".git").is_dir())
            self.assertTrue((box.workspace / "src/calc.py").is_file())
            self.assertEqual(box.artifacts.parent, box.workspace.parent)
            self.assertFalse(box.artifacts.is_relative_to(box.workspace))
        self.assertFalse(root.exists())

    def test_keep_retains_sandbox(self) -> None:
        manifest = get_demo("stale-proof")
        with create_sandbox(manifest, keep=True) as box:
            root = box.root
        self.assertTrue(root.is_dir())
        shutil.rmtree(root)

    def test_rejects_missing_git(self) -> None:
        with mock.patch("aet.demo.sandbox.shutil.which", return_value=None):
            with self.assertRaisesRegex(DemoUnavailable, "Git is required"):
                with create_sandbox(get_demo("stale-proof")):
                    pass

    def test_resolve_path_rejects_escape(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(DemoInvariantError, "escapes"):
                resolve_workspace_path(root, "../outside")

    @unittest.skipIf(os.name == "nt", "symlink creation may require Windows privileges")
    def test_rejects_fixture_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory)
            (fixture / "src").mkdir()
            (fixture / "src/real.py").write_text("value = 1\n")
            (fixture / "src/link.py").symlink_to("real.py")
            with mock.patch(
                "aet.demo.sandbox.fixture_resource",
                return_value=fixture,
            ):
                with self.assertRaisesRegex(DemoInvariantError, "symlink"):
                    with create_sandbox(get_demo("stale-proof")):
                        pass

    def test_workspace_supports_non_ascii_and_spaces(self) -> None:
        manifest = get_demo("stale-proof")
        with create_sandbox(manifest) as box:
            target = box.workspace / "中文 path.txt"
            target.write_text("ok", encoding="utf-8")
            self.assertEqual(target.read_text(encoding="utf-8"), "ok")
