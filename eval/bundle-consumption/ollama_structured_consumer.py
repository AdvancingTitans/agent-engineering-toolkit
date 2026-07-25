#!/usr/bin/env python3
"""Local prompt-only consumer using Ollama structured output and no AET SDK."""

from __future__ import annotations

import json
import sys
import urllib.request
from typing import Any


REVIEW_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["reviews"],
    "properties": {
        "reviews": {
            "type": "array",
            "minItems": 10,
            "maxItems": 10,
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["scenario_id", "review"],
                "properties": {
                    "scenario_id": {"type": "string"},
                    "review": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "protocol",
                            "bundle_id",
                            "conclusions",
                            "unresolved_questions",
                        ],
                        "properties": {
                            "protocol": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["name", "version"],
                                "properties": {
                                    "name": {
                                        "type": "string",
                                        "const": "portable-review-result",
                                    },
                                    "version": {"type": "string", "const": "1.0"},
                                },
                            },
                            "bundle_id": {"type": "string"},
                            "conclusions": {
                                "type": "array",
                                "minItems": 1,
                                "maxItems": 1,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "required": [
                                        "id",
                                        "statement",
                                        "disposition",
                                        "claim_refs",
                                        "evidence_refs",
                                        "counter_evidence_refs",
                                        "reasoning_summary",
                                        "limitations",
                                    ],
                                    "properties": {
                                        "id": {"type": "string"},
                                        "statement": {"type": "string"},
                                        "disposition": {
                                            "type": "string",
                                            "enum": [
                                                "accept",
                                                "request_change",
                                                "request_investigation",
                                                "unknown",
                                            ],
                                        },
                                        "claim_refs": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "evidence_refs": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "counter_evidence_refs": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "reasoning_summary": {"type": "string"},
                                        "limitations": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "next_action": {"type": "string"},
                                    },
                                },
                            },
                            "unresolved_questions": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                    },
                },
            },
        }
    },
}


def main() -> None:
    prompt = sys.stdin.read()
    if not prompt:
        raise SystemExit("local structured consumer requires a prompt on stdin")
    request = urllib.request.Request(
        "http://127.0.0.1:11434/api/generate",
        data=json.dumps(
            {
                "model": "qwen3:8b",
                "prompt": prompt,
                "format": REVIEW_SCHEMA,
                "stream": False,
                "think": False,
                "options": {"temperature": 0, "num_ctx": 40000},
            },
            separators=(",", ":"),
        ).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    with opener.open(request, timeout=600) as response:
        envelope = json.loads(response.read())
    content = envelope.get("response")
    if not isinstance(content, str):
        raise SystemExit("local structured consumer returned no response text")
    value = json.loads(content)
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
    )


if __name__ == "__main__":
    main()
