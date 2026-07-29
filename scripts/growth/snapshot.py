#!/usr/bin/env python3
"""Collect an aggregate, privacy-preserving growth baseline."""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from common import USER_AGENT, get_json, utc_now, write_json
from models import GrowthSnapshot, MetricValue, metric


GITHUB_API = "https://api.github.com"
PYPI_API = "https://pypi.org/pypi/agent-engineering-toolkit/json"
SKILLS_API = "https://skills.sh/api/search"
SKILL_IDS = ("aet-check", "aet-scope", "aet-proof", "aet-fresh", "aet-plan")


def _github_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _known(value: Any, source: str, observed_at: str) -> MetricValue:
    return metric(
        status="KNOWN",
        value=value,
        source=source,
        observed_at=observed_at,
    )


def _unknown(
    source: str,
    observed_at: str,
    diagnostic: str,
    *,
    status: str = "UNKNOWN",
) -> MetricValue:
    return metric(
        status=status,  # type: ignore[arg-type]
        value=None,
        source=source,
        observed_at=observed_at,
        diagnostic=diagnostic,
    )


def _collect_skills(observed_at: str) -> tuple[MetricValue, dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    diagnostics: list[str] = []
    for skill_id in SKILL_IDS:
        url = f"{SKILLS_API}?q={skill_id}"
        status, payload, diagnostic = get_json(url, retries=1)
        if status != "KNOWN" or not isinstance(payload, dict):
            diagnostics.append(f"{skill_id}: {diagnostic or status}")
            continue
        matches = [
            item
            for item in payload.get("skills", [])
            if isinstance(item, dict)
            and item.get("source", "").lower()
            == "advancingtitans/agent-engineering-toolkit"
            and item.get("skillId") == skill_id
        ]
        discovered.extend(matches)
    if diagnostics:
        return (
            _unknown(
                "skills.sh search API",
                observed_at,
                "; ".join(diagnostics),
                status="UNAVAILABLE",
            ),
            {"status": "UNAVAILABLE", "skills": discovered, "diagnostics": diagnostics},
        )
    if len(discovered) != len(SKILL_IDS):
        return (
            _unknown(
                "skills.sh search API",
                observed_at,
                "one or more AET Skills are not indexed",
                status="UNAVAILABLE",
            ),
            {
                "status": "UNAVAILABLE",
                "expected_skill_ids": list(SKILL_IDS),
                "skills": discovered,
                "diagnostic": "one or more AET Skills are not indexed",
            },
        )
    installs = sum(
        item["installs"]
        for item in discovered
        if isinstance(item.get("installs"), int)
    )
    return (
        _known(installs, "skills.sh search API", observed_at),
        {"status": "KNOWN", "skills": discovered},
    )


def collect_snapshot(repo: str, token: str | None) -> GrowthSnapshot:
    observed_at = utc_now()
    headers = _github_headers(token)
    repo_url = f"{GITHUB_API}/repos/{repo}"
    repo_status, repo_data, repo_diagnostic = get_json(repo_url, headers=headers)
    if repo_status != "KNOWN" or not isinstance(repo_data, dict):
        raise RuntimeError(
            f"public repository metadata is unavailable: {repo_diagnostic or repo_status}"
        )

    stars = _known(repo_data.get("stargazers_count"), repo_url, observed_at)
    forks = _known(repo_data.get("forks_count"), repo_url, observed_at)
    watchers = _known(repo_data.get("subscribers_count"), repo_url, observed_at)
    open_issues = _known(repo_data.get("open_issues_count"), repo_url, observed_at)

    contributors_url = f"{repo_url}/contributors?per_page=100&anon=true"
    contributor_status, contributor_data, contributor_diagnostic = get_json(
        contributors_url, headers=headers
    )
    if contributor_status == "KNOWN" and isinstance(contributor_data, list):
        contributors = _known(len(contributor_data), contributors_url, observed_at)
    else:
        contributors = _unknown(
            contributors_url,
            observed_at,
            contributor_diagnostic or contributor_status,
            status="UNAVAILABLE",
        )

    pulls_url = f"{repo_url}/pulls?state=all&per_page=100"
    pulls_status, pulls_data, pulls_diagnostic = get_json(pulls_url, headers=headers)
    if pulls_status == "KNOWN" and isinstance(pulls_data, list):
        pull_requests = _known(len(pulls_data), pulls_url, observed_at)
    else:
        pull_requests = _unknown(
            pulls_url,
            observed_at,
            pulls_diagnostic or pulls_status,
            status="UNAVAILABLE",
        )

    traffic = _collect_traffic(repo_url, headers, observed_at, token)
    release_downloads, release_state = _collect_release(
        repo_url, headers, observed_at
    )
    pypi_state = _collect_pypi()
    skills_installs, skills_state = _collect_skills(observed_at)
    community_state = _collect_community(repo_url, headers)
    repository_state = {
        key: repo_data.get(key)
        for key in (
            "default_branch",
            "size",
            "has_discussions",
            "has_pages",
            "homepage",
            "topics",
            "description",
            "archived",
            "visibility",
            "pushed_at",
            "updated_at",
        )
    }

    return GrowthSnapshot(
        schema_version="aet-growth-snapshot/v1",
        repository=repo,
        observed_at=observed_at,
        stars=stars,
        forks=forks,
        watchers=watchers,
        open_issues=open_issues,
        contributors=contributors,
        pull_requests=pull_requests,
        traffic_views=traffic["views"],
        traffic_unique_visitors=traffic["unique_visitors"],
        clones=traffic["clones"],
        release_downloads=release_downloads,
        skills_installs=skills_installs,
        referrers=traffic["referrers"],
        repository_state=repository_state,
        release_state=release_state,
        pypi_state=pypi_state,
        skills_state=skills_state,
        community_state=community_state,
    )


def _collect_traffic(
    repo_url: str,
    headers: dict[str, str],
    observed_at: str,
    token: str | None,
) -> dict[str, Any]:
    if not token:
        reason = "GH_TOKEN is not configured; GitHub Traffic requires push access"
        return {
            "views": _unknown(f"{repo_url}/traffic/views", observed_at, reason),
            "unique_visitors": _unknown(
                f"{repo_url}/traffic/views", observed_at, reason
            ),
            "clones": _unknown(f"{repo_url}/traffic/clones", observed_at, reason),
            "referrers": [],
        }

    views_status, views_data, views_diagnostic = get_json(
        f"{repo_url}/traffic/views", headers=headers
    )
    clones_status, clones_data, clones_diagnostic = get_json(
        f"{repo_url}/traffic/clones", headers=headers
    )
    ref_status, ref_data, _ = get_json(
        f"{repo_url}/traffic/popular/referrers", headers=headers
    )
    mapped_views = _map_traffic_metric(
        views_status,
        views_data,
        "count",
        f"{repo_url}/traffic/views",
        observed_at,
        views_diagnostic,
    )
    mapped_uniques = _map_traffic_metric(
        views_status,
        views_data,
        "uniques",
        f"{repo_url}/traffic/views",
        observed_at,
        views_diagnostic,
    )
    mapped_clones = _map_traffic_metric(
        clones_status,
        clones_data,
        "count",
        f"{repo_url}/traffic/clones",
        observed_at,
        clones_diagnostic,
    )
    return {
        "views": mapped_views,
        "unique_visitors": mapped_uniques,
        "clones": mapped_clones,
        "referrers": ref_data
        if ref_status == "KNOWN" and isinstance(ref_data, list)
        else [],
    }


def _map_traffic_metric(
    status: str,
    payload: Any,
    key: str,
    source: str,
    observed_at: str,
    diagnostic: str | None,
) -> MetricValue:
    if status == "KNOWN" and isinstance(payload, dict) and isinstance(
        payload.get(key), int
    ):
        return _known(payload[key], source, observed_at)
    mapped = "RATE_LIMITED" if status == "RATE_LIMITED" else "UNKNOWN"
    return _unknown(source, observed_at, diagnostic or status, status=mapped)


def _collect_release(
    repo_url: str, headers: dict[str, str], observed_at: str
) -> tuple[MetricValue, dict[str, Any]]:
    url = f"{repo_url}/releases/latest"
    status, payload, diagnostic = get_json(url, headers=headers)
    if status != "KNOWN" or not isinstance(payload, dict):
        return (
            _unknown(
                url,
                observed_at,
                diagnostic or status,
                status="UNAVAILABLE",
            ),
            {"status": "UNAVAILABLE", "diagnostic": diagnostic or status},
        )
    assets = [
        {
            "name": asset.get("name"),
            "size": asset.get("size"),
            "download_count": asset.get("download_count"),
        }
        for asset in payload.get("assets", [])
        if isinstance(asset, dict)
    ]
    total = sum(
        asset["download_count"]
        for asset in assets
        if isinstance(asset.get("download_count"), int)
    )
    return (
        _known(total, url, observed_at),
        {
            "status": "KNOWN",
            "tag_name": payload.get("tag_name"),
            "published_at": payload.get("published_at"),
            "draft": payload.get("draft"),
            "prerelease": payload.get("prerelease"),
            "assets": assets,
        },
    )


def _collect_pypi() -> dict[str, Any]:
    status, payload, diagnostic = get_json(PYPI_API)
    if status != "KNOWN" or not isinstance(payload, dict):
        return {
            "status": "UNAVAILABLE",
            "diagnostic": diagnostic or status,
            "source": PYPI_API,
        }
    info = payload.get("info", {})
    ownership = payload.get("ownership", {})
    return {
        "status": "KNOWN",
        "source": PYPI_API,
        "name": info.get("name") if isinstance(info, dict) else None,
        "version": info.get("version") if isinstance(info, dict) else None,
        "roles": ownership.get("roles", []) if isinstance(ownership, dict) else [],
        "downloads_status": "UNAVAILABLE",
        "downloads_diagnostic": "PyPI JSON does not provide current download totals",
    }


def _collect_community(
    repo_url: str, headers: dict[str, str]
) -> dict[str, Any]:
    status, payload, diagnostic = get_json(
        f"{repo_url}/community/profile", headers=headers
    )
    if status != "KNOWN" or not isinstance(payload, dict):
        return {"status": "UNAVAILABLE", "diagnostic": diagnostic or status}
    files = payload.get("files", {})
    return {
        "status": "KNOWN",
        "health_percentage": payload.get("health_percentage"),
        "files": sorted(files) if isinstance(files, dict) else [],
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Collect aggregate repository growth metrics without product telemetry."
    )
    parser.add_argument("--repo", required=True, help="GitHub owner/repository")
    parser.add_argument("--output", required=True, type=Path)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        snapshot = collect_snapshot(args.repo, os.environ.get("GH_TOKEN"))
        write_json(args.output, snapshot.to_dict())
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as error:
        print(f"growth snapshot failed: {error}", file=sys.stderr)
        return 1
    print(f"Wrote {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
