import copy
import json
import unittest
from importlib import resources

from aet.demo.errors import DemoInvariantError
from aet.demo.registry import get_demo, list_demos, parse_manifest


def valid_manifest() -> dict:
    path = resources.files("aet.demo") / "fixtures/stale-proof/manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


class DemoRegistryTests(unittest.TestCase):
    def test_lists_and_loads_installed_manifest(self) -> None:
        demos = list_demos()
        self.assertEqual([item.demo_id for item in demos], ["stale-proof"])
        self.assertEqual(get_demo("stale-proof").command[0], "${PYTHON}")

    def test_unknown_demo_lists_available_id(self) -> None:
        with self.assertRaisesRegex(DemoInvariantError, "available demos"):
            get_demo("missing")

    def test_rejects_shell_string_and_unknown_field(self) -> None:
        raw = valid_manifest()
        raw["command"] = "${PYTHON} -m unittest"
        with self.assertRaisesRegex(DemoInvariantError, "token array"):
            parse_manifest(raw)
        raw = valid_manifest()
        raw["unexpected"] = True
        with self.assertRaisesRegex(DemoInvariantError, "fields"):
            parse_manifest(raw)

    def test_rejects_path_traversal_and_unknown_placeholder(self) -> None:
        raw = valid_manifest()
        raw["mutations"][0]["path"] = "../outside.py"
        with self.assertRaisesRegex(DemoInvariantError, "declared root"):
            parse_manifest(raw)
        raw = valid_manifest()
        raw["command"][0] = "${SHELL}"
        with self.assertRaisesRegex(DemoInvariantError, "placeholder"):
            parse_manifest(raw)

    def test_rejects_unknown_operation_and_bad_sha(self) -> None:
        raw = valid_manifest()
        raw["mutations"][0]["operation"] = "run"
        with self.assertRaisesRegex(DemoInvariantError, "operation"):
            parse_manifest(raw)
        raw = valid_manifest()
        raw["mutations"][0]["expected_old_sha256"] = "not-a-sha"
        with self.assertRaisesRegex(DemoInvariantError, "sha256"):
            parse_manifest(raw)

    def test_manifest_parse_does_not_mutate_input(self) -> None:
        raw = valid_manifest()
        original = copy.deepcopy(raw)
        parse_manifest(raw)
        self.assertEqual(raw, original)
