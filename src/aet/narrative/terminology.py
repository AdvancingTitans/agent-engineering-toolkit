"""Deterministic language routing without changing machine evidence."""

from __future__ import annotations

import re

SUPPORTED_LANGUAGES = ("en", "zh-CN")
_CHINESE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]")


def select_language(
    *,
    request: str = "",
    slash_command: bool = False,
) -> str:
    """Use Chinese only for a Chinese slash-command request; otherwise English."""
    if slash_command and _CHINESE.search(request):
        return "zh-CN"
    return "en"
