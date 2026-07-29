import unittest
from importlib import resources
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


class DemoWheelContractTests(unittest.TestCase):
    def test_fixture_is_a_package_resource_and_package_data_is_explicit(self) -> None:
        fixture = resources.files("aet.demo") / "fixtures/stale-proof/repo/src/calc.py"
        self.assertTrue(fixture.is_file())
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertIn("demo/fixtures/stale-proof/manifest.json", pyproject)
        self.assertIn('"share/aet/schemas/demo/v1"', pyproject)
        attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
        self.assertIn("src/aet/demo/fixtures/** text eol=lf", attributes)
        verifier = (ROOT / "scripts/verify_installed_demo.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('{"PASS", "PASS_WITH_WARNING"}', verifier)
