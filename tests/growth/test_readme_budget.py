import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/growth"))

from verify_readme_budget import HERO_COMMAND, verify


class ReadmeBudgetTests(unittest.TestCase):
    def test_current_readme_passes(self) -> None:
        self.assertEqual(verify(ROOT / "README.md", 250), [])

    def test_reports_budget_command_and_boundary_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "README.md"
            path.write_text("\n".join(["line"] * 61) + "\n", encoding="utf-8")
            failures = verify(path, 60)
        self.assertTrue(any("exceeds" in item for item in failures))
        self.assertTrue(any("hero command" in item for item in failures))
        self.assertTrue(any("UNKNOWN" in item for item in failures))

    def test_rejects_source_only_install_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "README.md"
            path.write_text(
                f"{HERO_COMMAND}\nUNKNOWN\nAET does not replace tests or CI\nuv tool install .\n",
                encoding="utf-8",
            )
            failures = verify(path, 250)
        self.assertTrue(any("source-only" in item for item in failures))
