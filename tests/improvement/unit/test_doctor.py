from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path

from aet.cli import main
from aet.improvement.cli.improve import doctor_bundle


ROOT = Path(__file__).resolve().parents[3]


class ImprovementDoctorTests(unittest.TestCase):
    def test_doctor_validates_portable_bundle(self) -> None:
        result = doctor_bundle(ROOT / "tests/fixtures/evidence-bundles/minimal")

        self.assertEqual(
            result,
            "Bundle loading OK\n"
            "Evidence reference OK\n"
            "Finding loading OK\n",
        )

    def test_doctor_cli(self) -> None:
        output = StringIO()

        with redirect_stdout(output):
            exit_code = main(
                [
                    "improvement",
                    "doctor",
                    str(ROOT / "tests/fixtures/evidence-bundles/minimal"),
                ]
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            output.getvalue(),
            "Bundle loading OK\n"
            "Evidence reference OK\n"
            "Finding loading OK\n",
        )


if __name__ == "__main__":
    unittest.main()
