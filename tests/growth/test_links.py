import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/growth"))

from check_links import check


class LinkCheckTests(unittest.TestCase):
    def test_current_local_links_pass(self) -> None:
        previous = Path.cwd()
        try:
            import os

            os.chdir(ROOT)
            self.assertEqual(check([Path("README.md"), Path("docs"), Path("site")]), [])
        finally:
            os.chdir(previous)

    def test_reports_missing_target_and_anchor(self) -> None:
        with tempfile.TemporaryDirectory(dir=ROOT) as directory:
            path = Path(directory)
            target = path / "target.md"
            target.write_text("# Present\n", encoding="utf-8")
            source = path / "source.md"
            source.write_text(
                "[missing](none.md)\n[anchor](target.md#absent)\n",
                encoding="utf-8",
            )
            failures = check([source])
        self.assertTrue(any("missing local target" in item for item in failures))
        self.assertTrue(any("missing Markdown anchor" in item for item in failures))
