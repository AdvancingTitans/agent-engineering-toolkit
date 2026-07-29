from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path

from aet.planning.errors import PlanningError, PlanningErrorCode
from aet.planning.models import PlanningConstraints
from aet.planning.source_navigator import SourceNavigator


class SourceNavigatorTests(unittest.TestCase):
    def test_python_symbol_hash_and_staleness(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            root = Path(raw)
            (root / "src").mkdir()
            source = root / "src/example.py"
            source.write_text("def run():\n    return 1\n", encoding="utf-8")
            navigator = SourceNavigator(
                root,
                PlanningConstraints(
                    allowed_paths=["src/**"],
                    protected_paths=[],
                    scope_status="RESOLVED",
                ),
            )
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            current = navigator.inspect_path(
                "src/example.py",
                expected_hash=digest,
                symbol="run",
            )
            self.assertEqual(current.site.read_status, "CONFIRMED")
            self.assertEqual((current.site.start_line, current.site.end_line), (1, 2))
            stale = navigator.inspect_path(
                "src/example.py",
                expected_hash="0" * 64,
            )
            self.assertEqual(stale.site.read_status, "STALE")

    def test_binary_missing_protected_and_symlink_escape(self) -> None:
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as external:
            root = Path(raw)
            (root / "src").mkdir()
            (root / "src/data.bin").write_bytes(b"\x00\x01")
            outside = Path(external) / "outside.py"
            outside.write_text("x = 1\n", encoding="utf-8")
            (root / "src/link.py").symlink_to(outside)
            navigator = SourceNavigator(
                root,
                PlanningConstraints(
                    allowed_paths=["src/**"],
                    protected_paths=["src/private/**"],
                    scope_status="RESOLVED",
                ),
            )
            self.assertEqual(
                navigator.inspect_path("src/data.bin").site.read_status,
                "UNSUPPORTED",
            )
            self.assertEqual(
                navigator.inspect_path("src/missing.py").site.read_status,
                "MISSING",
            )
            with self.assertRaises(PlanningError) as protected:
                navigator.inspect_path("src/private/key.py")
            self.assertEqual(protected.exception.code, PlanningErrorCode.PROTECTED_PATH)
            with self.assertRaises(PlanningError) as escaped:
                navigator.inspect_path("src/link.py")
            self.assertEqual(escaped.exception.code, PlanningErrorCode.PATH_ESCAPE)


if __name__ == "__main__":
    unittest.main()
