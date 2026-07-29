import json
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
GROWTH = ROOT / "scripts/growth"
sys.path.insert(0, str(GROWTH))

import common
import snapshot


REPO = {
    "stargazers_count": 2,
    "forks_count": 0,
    "subscribers_count": 0,
    "open_issues_count": 1,
    "default_branch": "main",
    "size": 89164,
    "has_discussions": False,
    "has_pages": False,
    "homepage": None,
    "topics": ["ai-agents"],
    "description": "description",
    "archived": False,
    "visibility": "public",
    "pushed_at": "2026-07-29T00:00:00Z",
    "updated_at": "2026-07-29T00:00:00Z",
}


def response(url: str, **kwargs):
    if url.endswith("/contributors?per_page=100&anon=true"):
        return "KNOWN", [{"login": "one"}, {"login": "two"}], None
    if "/pulls?" in url:
        return "KNOWN", [{}, {}, {}], None
    if url.endswith("/releases/latest"):
        return (
            "KNOWN",
            {
                "tag_name": "v1.17.0",
                "published_at": "2026-07-29T00:00:00Z",
                "draft": False,
                "prerelease": False,
                "assets": [{"name": "a.whl", "size": 10, "download_count": 4}],
            },
            None,
        )
    if url == snapshot.PYPI_API:
        return (
            "KNOWN",
            {
                "info": {"name": "agent-engineering-toolkit", "version": "1.11.1"},
                "ownership": {"roles": [{"role": "Owner", "user": "owner"}]},
            },
            None,
        )
    if url.startswith(snapshot.SKILLS_API):
        return "KNOWN", {"skills": []}, None
    if url.endswith("/community/profile"):
        return "KNOWN", {"health_percentage": 57, "files": {"readme": {}}}, None
    if url.endswith("/traffic/views"):
        return "UNAVAILABLE", None, "HTTP 403 Forbidden"
    if url.endswith("/traffic/clones"):
        return "UNAVAILABLE", None, "HTTP 403 Forbidden"
    if url.endswith("/traffic/popular/referrers"):
        return "UNAVAILABLE", None, "HTTP 403 Forbidden"
    if url.endswith("AdvancingTitans/agent-engineering-toolkit"):
        return "KNOWN", REPO, None
    raise AssertionError(url)


class GrowthSnapshotTests(unittest.TestCase):
    def test_public_snapshot_preserves_unknown_traffic_and_unavailable_skills(self) -> None:
        with mock.patch("snapshot.get_json", side_effect=response):
            result = snapshot.collect_snapshot(
                "AdvancingTitans/agent-engineering-toolkit",
                token=None,
            ).to_dict()
        self.assertEqual(result["stars"]["value"], 2)
        self.assertEqual(result["contributors"]["value"], 2)
        self.assertEqual(result["pull_requests"]["value"], 3)
        self.assertEqual(result["traffic_views"]["status"], "UNKNOWN")
        self.assertIsNone(result["traffic_views"]["value"])
        self.assertEqual(result["release_downloads"]["value"], 4)
        self.assertEqual(result["skills_installs"]["status"], "UNAVAILABLE")
        self.assertEqual(result["pypi_state"]["version"], "1.11.1")

    def test_traffic_403_with_token_stays_unknown_not_zero(self) -> None:
        with mock.patch("snapshot.get_json", side_effect=response):
            result = snapshot.collect_snapshot(
                "AdvancingTitans/agent-engineering-toolkit",
                token="redacted",
            ).to_dict()
        self.assertEqual(result["traffic_views"]["status"], "UNKNOWN")
        self.assertIsNone(result["clones"]["value"])
        self.assertEqual(result["referrers"], [])

    def test_rate_limit_maps_without_retry_loop_or_zero_fill(self) -> None:
        value = snapshot._map_traffic_metric(
            "RATE_LIMITED",
            None,
            "count",
            "source",
            "2026-01-01T00:00:00Z",
            "reset=1",
        )
        self.assertEqual(value.status, "RATE_LIMITED")
        self.assertIsNone(value.value)

    def test_common_http_status_mapping(self) -> None:
        for code, expected in ((404, "UNAVAILABLE"), (429, "RATE_LIMITED")):
            error = urllib.error.HTTPError(
                "https://example.invalid",
                code,
                "error",
                {},
                None,
            )
            with self.subTest(code=code):
                with mock.patch(
                    "common.urllib.request.urlopen",
                    side_effect=error,
                ):
                    status, value, diagnostic = common.get_json(
                        "https://example.invalid", retries=0
                    )
                self.assertEqual(status, expected)
                self.assertIsNone(value)
                self.assertIn(str(code), diagnostic)

    def test_snapshot_example_never_zero_fills_unknown(self) -> None:
        example = json.loads(
            (ROOT / "ops/growth/metrics/baseline.example.json").read_text()
        )
        for key, value in example.items():
            if isinstance(value, dict) and value.get("status") != "KNOWN":
                self.assertIsNone(value["value"], key)
