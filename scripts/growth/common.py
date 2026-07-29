"""Shared, read-only helpers for maintainer growth snapshots."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


USER_AGENT = "aet-growth-snapshot/1.0"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    retries: int = 2,
    timeout: float = 20.0,
) -> tuple[str, Any, str | None]:
    request_headers = {"Accept": "application/json", "User-Agent": USER_AGENT}
    request_headers.update(headers or {})
    for attempt in range(retries + 1):
        request = urllib.request.Request(url, headers=request_headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return "KNOWN", json.load(response), None
        except urllib.error.HTTPError as error:
            if error.code == 429:
                return "RATE_LIMITED", None, _http_diagnostic(error)
            if error.code in {401, 403, 404}:
                return "UNAVAILABLE", None, _http_diagnostic(error)
            if error.code >= 500 and attempt < retries:
                time.sleep(0.25 * (2**attempt))
                continue
            return "UNAVAILABLE", None, _http_diagnostic(error)
        except (OSError, ValueError) as error:
            if attempt < retries:
                time.sleep(0.25 * (2**attempt))
                continue
            return "UNAVAILABLE", None, f"{type(error).__name__}: {error}"
    return "UNAVAILABLE", None, "request retry budget exhausted"


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _http_diagnostic(error: urllib.error.HTTPError) -> str:
    reset = error.headers.get("X-RateLimit-Reset")
    suffix = f"; rate_limit_reset={reset}" if reset else ""
    return f"HTTP {error.code} {error.reason}{suffix}"
