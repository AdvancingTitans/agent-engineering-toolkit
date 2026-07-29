import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from aet.cli import main


class DemoCliTests(unittest.TestCase):
    def test_list_and_json_run(self) -> None:
        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(main(["demo", "list"]), 0)
        self.assertIn("stale-proof", output.getvalue())

        output = StringIO()
        with redirect_stdout(output):
            self.assertEqual(
                main(["demo", "stale-proof", "--format", "json"]),
                0,
            )
        self.assertEqual(json.loads(output.getvalue())["overall_status"], "PASS")

    def test_markdown_output_file(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "result.md"
            self.assertEqual(
                main(
                    [
                        "demo",
                        "stale-proof",
                        "--format",
                        "markdown",
                        "--output",
                        str(output),
                    ]
                ),
                0,
            )
            self.assertIn("# AET stale-proof demo", output.read_text())

    def test_invalid_demo_and_missing_id_return_usage_exit(self) -> None:
        error = StringIO()
        with redirect_stderr(error):
            self.assertEqual(main(["demo", "not-real"]), 64)
        self.assertIn("unknown demo", error.getvalue())

        with redirect_stderr(StringIO()):
            self.assertEqual(main(["demo"]), 64)

    def test_list_rejects_run_options(self) -> None:
        with redirect_stderr(StringIO()):
            self.assertEqual(main(["demo", "list", "--keep"]), 64)
