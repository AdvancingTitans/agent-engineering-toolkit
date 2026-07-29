import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts/growth"))

from validate_launch import validate


class LaunchValidationTests(unittest.TestCase):
    def test_current_conversion_and_distribution_assets_pass(self) -> None:
        previous = Path.cwd()
        try:
            import os

            os.chdir(ROOT)
            self.assertEqual(validate("conversion", strict=True), [])
            self.assertEqual(validate("distribution", strict=True), [])
            self.assertEqual(validate("launch", strict=True), [])
        finally:
            os.chdir(previous)
