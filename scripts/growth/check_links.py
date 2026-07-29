#!/usr/bin/env python3
"""Offline validation for local Markdown and HTML links."""

from __future__ import annotations

import argparse
import html.parser
import re
import sys
import urllib.parse
from pathlib import Path
from typing import Iterable


MARKDOWN_LINK = re.compile(r"!?\[[^\]]*\]\(([^)]+)\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*$", re.MULTILINE)
SCHEMES = ("http://", "https://", "mailto:", "data:", "javascript:")


class _HTMLLinks(html.parser.HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        for name in ("href", "src"):
            if name in values:
                self.links.append(values[name])


def _files(paths: Iterable[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(
                candidate
                for candidate in path.rglob("*")
                if candidate.is_file()
                and candidate.suffix.lower() in {".md", ".html"}
            )
        else:
            found.append(path)
    return sorted(set(found))


def _slug(value: str) -> str:
    value = re.sub(r"<[^>]+>", "", value)
    value = re.sub(r"[^\w\- ]", "", value, flags=re.UNICODE).strip().lower()
    return re.sub(r"[\s\-]+", "-", value)


def _anchors(path: Path) -> set[str]:
    if path.suffix.lower() != ".md":
        return set()
    text = path.read_text(encoding="utf-8")
    return {_slug(match) for match in HEADING.findall(text)}


def check(paths: Iterable[Path]) -> list[str]:
    failures: list[str] = []
    root = Path.cwd().resolve()
    for path in _files(paths):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as error:
            failures.append(f"{path}: cannot read: {error}")
            continue
        if path.suffix.lower() == ".md":
            links = [match.group(1).strip().split()[0] for match in MARKDOWN_LINK.finditer(text)]
        else:
            parser = _HTMLLinks()
            parser.feed(text)
            links = parser.links
        for raw in links:
            if not raw or raw.startswith(SCHEMES):
                continue
            decoded = urllib.parse.unquote(raw)
            target_value, _, fragment = decoded.partition("#")
            if not target_value:
                target = path.resolve()
            elif target_value.startswith("/"):
                failures.append(f"{path}: root-relative local link is not portable: {raw}")
                continue
            else:
                target = (path.parent / target_value).resolve()
            try:
                target.relative_to(root)
            except ValueError:
                failures.append(f"{path}: local link escapes repository: {raw}")
                continue
            if target.is_dir():
                if path.suffix.lower() == ".html" and (target / "index.html").is_file():
                    target = target / "index.html"
                elif not target.exists():
                    failures.append(f"{path}: missing local target: {raw}")
                    continue
            elif not target.is_file():
                failures.append(f"{path}: missing local target: {raw}")
                continue
            if fragment and target.suffix.lower() == ".md":
                if _slug(fragment) not in _anchors(target):
                    failures.append(f"{path}: missing Markdown anchor: {raw}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=Path)
    args = parser.parse_args(argv)
    failures = check(args.paths)
    if failures:
        print("\n".join(failures), file=sys.stderr)
        return 1
    print(f"Local link check PASS: {len(_files(args.paths))} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
