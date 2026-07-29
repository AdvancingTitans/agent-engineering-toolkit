"""Regression check for the deliberately flawed README sample."""

from __future__ import annotations

import unittest

from tool_result import normalize_findings


class EmptyToolResultTests(unittest.TestCase):
    def test_empty_result_remains_non_evidence(self) -> None:
        self.assertEqual(
            normalize_findings([]),
            {"status": "no_evidence", "facts": []},
        )


if __name__ == "__main__":
    unittest.main()
