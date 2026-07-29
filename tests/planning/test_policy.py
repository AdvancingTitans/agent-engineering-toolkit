from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aet.planning.errors import PlanningError, PlanningErrorCode
from aet.planning.models import PlanningConstraints
from aet.planning.policy import assert_path_allowed, resolve_workspace_path


class PlanningPolicyTests(unittest.TestCase):
    def setUp(self) -> None:
        self.constraints = PlanningConstraints(
            allowed_paths=["src/**"],
            protected_paths=["src/generated/**"],
            scope_status="RESOLVED",
        )

    def test_scope_and_protected_precedence(self) -> None:
        self.assertEqual(
            assert_path_allowed("src/a.py", self.constraints),
            "src/a.py",
        )
        with self.assertRaises(PlanningError) as protected:
            assert_path_allowed("src/generated/a.py", self.constraints)
        self.assertEqual(protected.exception.code, PlanningErrorCode.PROTECTED_PATH)
        with self.assertRaises(PlanningError) as outside:
            assert_path_allowed("tests/a.py", self.constraints)
        self.assertEqual(outside.exception.code, PlanningErrorCode.EVIDENCE_REQUIRED)

    def test_symlink_escape_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw, tempfile.TemporaryDirectory() as external:
            root = Path(raw)
            target = Path(external) / "secret.py"
            target.write_text("secret = True\n", encoding="utf-8")
            (root / "src").mkdir()
            (root / "src/link.py").symlink_to(target)
            with self.assertRaises(PlanningError) as raised:
                resolve_workspace_path(root, "src/link.py")
            self.assertEqual(raised.exception.code, PlanningErrorCode.PATH_ESCAPE)


if __name__ == "__main__":
    unittest.main()
