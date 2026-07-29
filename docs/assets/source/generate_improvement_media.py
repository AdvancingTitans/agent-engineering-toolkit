#!/usr/bin/env python3
"""Generate bilingual README case-study SVGs and staged GIF frames."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from html import escape
from pathlib import Path


BLUE = "#2563eb"
PURPLE = "#7c3aed"
GREEN = "#059669"
RED = "#dc2626"
AMBER = "#d97706"
INK = "#111827"
MUTED = "#6b7280"
LINE = "#d1d5db"


def _start(title: str) -> list[str]:
    return [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="900" '
            'viewBox="0 0 1600 900" role="img" '
            f'aria-label="{escape(title)}" data-generator="fireworks-tech-graph" '
            'data-schema-version="1" data-style-id="1" '
            'data-visual-theme="Flat Icon" data-diagram-type="architecture" '
            'data-semantic-profile="generic" data-semantic-valid="true" '
            'data-quality-profile="showcase">'
        ),
        "<defs>",
        (
            '<marker id="arrow-blue" markerWidth="10" markerHeight="7" '
            'refX="9" refY="3.5" orient="auto"><polygon '
            f'points="0 0,10 3.5,0 7" fill="{BLUE}"/></marker>'
        ),
        (
            '<marker id="arrow-purple" markerWidth="10" markerHeight="7" '
            'refX="9" refY="3.5" orient="auto"><polygon '
            f'points="0 0,10 3.5,0 7" fill="{PURPLE}"/></marker>'
        ),
        (
            '<marker id="arrow-green" markerWidth="10" markerHeight="7" '
            'refX="9" refY="3.5" orient="auto"><polygon '
            f'points="0 0,10 3.5,0 7" fill="{GREEN}"/></marker>'
        ),
        (
            '<marker id="arrow-red" markerWidth="10" markerHeight="7" '
            'refX="9" refY="3.5" orient="auto"><polygon '
            f'points="0 0,10 3.5,0 7" fill="{RED}"/></marker>'
        ),
        (
            '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="8" stdDeviation="10" '
            'flood-color="#0f172a" flood-opacity=".10"/></filter>'
        ),
        (
            '<style>text{font-family:"Helvetica Neue",Helvetica,Arial,'
            '"PingFang SC","Microsoft YaHei",sans-serif}'
            '.mono{font-family:"SFMono-Regular",Consolas,monospace}</style>'
        ),
        "</defs>",
        '<rect width="1600" height="900" fill="#ffffff" data-graph-role="background"/>',
        '<rect width="1600" height="92" fill="#f8fafc" data-graph-role="decoration" data-owner="canvas"/>',
    ]


def _card(
    out: list[str],
    *,
    node_id: str,
    x: int,
    y: int,
    width: int,
    height: int,
    title: str,
    subtitle: str,
    stroke: str,
    fill: str,
    role: str = "node",
) -> None:
    identity = (
        f'data-node-id="{node_id}"'
        if role == "node"
        else f'data-container-id="{node_id}"'
    )
    out.extend(
        [
            (
                f'<g data-graph-role="{role}" {identity} '
                f'data-graph-bounds="{x},{y},{x + width},{y + height}" '
                'filter="url(#shadow)">'
            ),
            (
                f'<rect x="{x}" y="{y}" width="{width}" height="{height}" '
                f'rx="14" fill="{fill}" stroke="{stroke}" stroke-width="2"'
                + (' data-graph-role="container"' if role == "container" else "")
                + "/>"
            ),
            (
                f'<text x="{x + 26}" y="{y + 42}" font-size="22" '
                f'font-weight="700" fill="{INK}">{escape(title)}</text>'
            ),
            (
                f'<text x="{x + 26}" y="{y + 72}" font-size="15" '
                f'fill="{MUTED}">{escape(subtitle)}</text>'
            ),
            "</g>",
        ]
    )


def _edge(
    out: list[str],
    *,
    edge_id: str,
    source: str,
    target: str,
    path: str,
    color: str,
    marker: str,
    label: str,
    label_x: int,
    label_y: int,
) -> None:
    out.extend(
        [
            (
                f'<path id="{edge_id}" data-graph-role="edge" '
                f'data-source="{source}" data-target="{target}" d="{path}" '
                f'fill="none" stroke="{color}" stroke-width="2.4" '
                f'stroke-linecap="round" stroke-linejoin="round" '
                f'marker-end="url(#{marker})"/>'
            ),
            (
                f'<text x="{label_x}" y="{label_y}" text-anchor="middle" '
                f'font-size="13" font-weight="600" fill="{color}">'
                f'{escape(label)}</text>'
            ),
        ]
    )


def _prompt_panel(out: list[str], zh: bool) -> None:
    title = "给人类与 Agent 的改进提示词" if zh else "Human + Agent improvement prompt"
    subtitle = "确定性派生；不是代码修改，也不是 Evidence" if zh else "deterministic derivation; not a code change or Evidence"
    _card(
        out,
        node_id="improvement-prompt",
        x=70,
        y=350,
        width=680,
        height=365,
        title=title,
        subtitle=subtitle,
        stroke=PURPLE,
        fill="#faf5ff",
        role="container",
    )
    rows = (
        [
            ("ISSUE", "IMP-001 · P1_HIGH · unsupported_claim", RED),
            ("EVIDENCE", "ev-empty-result-regression", BLUE),
            ("ALLOWED", "sample_project/tool_result.py", GREEN),
            ("VERIFY", "python …/test_tool_result.py", AMBER),
            ("STATUS", "PROPOSED · 遇到缺失引用立即停止", PURPLE),
        ]
        if zh
        else [
            ("ISSUE", "IMP-001 · P1_HIGH · unsupported_claim", RED),
            ("EVIDENCE", "ev-empty-result-regression", BLUE),
            ("ALLOWED", "sample_project/tool_result.py", GREEN),
            ("VERIFY", "python …/test_tool_result.py", AMBER),
            ("STATUS", "PROPOSED · stop on missing references", PURPLE),
        ]
    )
    for index, (label, value, color) in enumerate(rows):
        y = 465 + index * 48
        out.extend(
            [
                f'<rect x="100" y="{y - 25}" width="102" height="32" rx="16" fill="{color}" fill-opacity=".12"/>',
                f'<text x="151" y="{y - 3}" text-anchor="middle" class="mono" font-size="12" font-weight="800" fill="{color}">{label}</text>',
                f'<text x="224" y="{y - 3}" class="mono" font-size="15" fill="{INK}">{escape(value)}</text>',
            ]
        )


def _atlas_panel(out: list[str], zh: bool) -> None:
    title = "可视化 Evidence Atlas" if zh else "Visual Evidence Atlas"
    subtitle = "同一 Bundle 的只读投影；反证与 UNKNOWN 始终可见" if zh else "read-only projection of the same Bundle; counter-evidence and UNKNOWN stay visible"
    _card(
        out,
        node_id="evidence-atlas",
        x=850,
        y=350,
        width=680,
        height=365,
        title=title,
        subtitle=subtitle,
        stroke=GREEN,
        fill="#f0fdf4",
        role="container",
    )
    nodes = [
        (900, 468, 170, 72, "UNSUPPORTED", "Claim", RED, "#fef2f2"),
        (1160, 440, 290, 92, "VERIFIED FAIL", "ev-empty-result-regression", GREEN, "#ecfdf5"),
        (1160, 590, 290, 72, "UNKNOWN", "improvement-chain", MUTED, "#f3f4f6"),
    ]
    for index, (x, y, width, height, status, label, stroke, fill) in enumerate(nodes):
        out.extend(
            [
                f'<g data-graph-role="node" data-node-id="atlas-{index}">',
                f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="12" fill="{fill}" stroke="{stroke}" stroke-width="2"/>',
                f'<text x="{x + width / 2:.0f}" y="{y + 29}" text-anchor="middle" class="mono" font-size="12" font-weight="800" fill="{stroke}">{status}</text>',
                f'<text x="{x + width / 2:.0f}" y="{y + 55}" text-anchor="middle" font-size="14" font-weight="650" fill="{INK}">{escape(label)}</text>',
                "</g>",
            ]
        )
    _edge(
        out,
        edge_id="atlas-counter",
        source="atlas-0",
        target="atlas-1",
        path="M1070 504H1160",
        color=RED,
        marker="arrow-red",
        label="反证" if zh else "contradicts",
        label_x=1115,
        label_y=492,
    )
    _edge(
        out,
        edge_id="atlas-unknown",
        source="atlas-1",
        target="atlas-2",
        path="M1305 532V590",
        color=GREEN,
        marker="arrow-green",
        label="不推断 Outcome" if zh else "no inferred outcome",
        label_x=1390,
        label_y=567,
    )


def render_case(language: str, destination: Path, *, phase: int = 6) -> None:
    zh = language == "zh-CN"
    title = "AET v1.16 · 证据驱动的代码改进案例" if zh else "AET v1.16 · Evidence-Grounded Code Improvement"
    subtitle = (
        "人类问 Agent“帮我审查项目”；AET 用同一份证据交付可执行提示词与可追溯图谱"
        if zh
        else "A human asks an Agent to review a project; one evidence source drives a bounded prompt and a traceable graph"
    )
    out = _start(title)
    out.extend(
        [
            f'<text x="60" y="47" font-size="28" font-weight="800" fill="{INK}">{escape(title)}</text>',
            f'<text x="60" y="76" font-size="15" fill="{MUTED}">{escape(subtitle)}</text>',
            f'<text x="1540" y="52" text-anchor="end" class="mono" font-size="13" font-weight="800" fill="{GREEN}">BUNDLE → PROMPT + ATLAS</text>',
        ]
    )
    if phase >= 1:
        _card(
            out,
            node_id="human-request",
            x=70,
            y=145,
            width=420,
            height=120,
            title="人类" if zh else "Human",
            subtitle=(
                "“请审查这个项目，并告诉我应该怎样安全改进。”"
                if zh
                else "“Review this project and tell me how to improve it safely.”"
            ),
            stroke=BLUE,
            fill="#eff6ff",
        )
    if phase >= 2:
        _card(
            out,
            node_id="portable-bundle",
            x=590,
            y=145,
            width=420,
            height=120,
            title="Portable Evidence Bundle",
            subtitle="Claim · Evidence · Counter-evidence · Proof · Freshness",
            stroke=GREEN,
            fill="#f0fdf4",
        )
        _edge(
            out,
            edge_id="request-to-bundle",
            source="human-request",
            target="portable-bundle",
            path="M490 205H590",
            color=BLUE,
            marker="arrow-blue",
            label="审查请求" if zh else "review request",
            label_x=540,
            label_y=192,
        )
    if phase >= 3:
        _prompt_panel(out, zh)
        _edge(
            out,
            edge_id="bundle-to-prompt",
            source="portable-bundle",
            target="improvement-prompt",
            path="M720 265V305H410V350",
            color=PURPLE,
            marker="arrow-purple",
            label="Issue + Constraint",
            label_x=555,
            label_y=294,
        )
    if phase >= 4:
        _atlas_panel(out, zh)
        _edge(
            out,
            edge_id="bundle-to-atlas",
            source="portable-bundle",
            target="evidence-atlas",
            path="M880 265V305H1190V350",
            color=GREEN,
            marker="arrow-green",
            label="Graph + Perspectives",
            label_x=1035,
            label_y=294,
        )
    if phase >= 5:
        badge = "共享 Evidence ID · 无权威回路" if zh else "shared Evidence IDs · no authority loop"
        out.extend(
            [
                '<rect x="585" y="752" width="430" height="42" rx="21" fill="#fff7ed" stroke="#d97706"/>',
                f'<text x="800" y="779" text-anchor="middle" class="mono" font-size="14" font-weight="800" fill="{AMBER}">{escape(badge)}</text>',
            ]
        )
    if phase >= 6:
        boundary = (
            "AET 不自动修改代码；Candidate 保持 PROPOSED，只有当前 Proof + 无回归比较才能成为 verified_improvement。"
            if zh
            else "AET does not edit code automatically; Candidate stays PROPOSED until current Proof and a no-regression comparison establish verified_improvement."
        )
        out.extend(
            [
                '<rect x="70" y="825" width="1460" height="48" rx="12" fill="#111827"/>',
                f'<text x="800" y="855" text-anchor="middle" font-size="15" font-weight="650" fill="#ffffff">{escape(boundary)}</text>',
            ]
        )
    out.append("</svg>")
    destination.write_text("\n".join(out), encoding="utf-8")


def _manifest(assets: Path) -> None:
    names = [
        "aet-improvement-case-en.svg",
        "aet-improvement-case-en.png",
        "aet-improvement-case-en.gif",
        "aet-improvement-case-zh-CN.svg",
        "aet-improvement-case-zh-CN.png",
        "aet-improvement-case-zh-CN.gif",
    ]
    media = []
    for name in names:
        path = assets / name
        if path.is_file():
            media.append(
                {
                    "path": f"docs/assets/{name}",
                    "bytes": path.stat().st_size,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                }
            )
    value = {
        "schema": "aet-readme-media/1.0",
        "release": "v1.16.0",
        "example": {
            "bundle_id": "bundle-empty-tool-result-review-v1",
            "finding_ref": "claim-empty-result-is-grounded",
            "evidence_ref": "ev-empty-result-regression",
            "issue_id": "IMP-001",
        },
        "motion": {
            "frames": 6,
            "frame_seconds": 1.35,
            "size": "1600x900",
        },
        "media": media,
    }
    (assets / "aet-improvement-media-manifest.json").write_text(
        json.dumps(value, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--frames", type=Path)
    args = parser.parse_args()
    args.assets.mkdir(parents=True, exist_ok=True)
    for language, suffix in (("en", "en"), ("zh-CN", "zh-CN")):
        render_case(
            language,
            args.assets / f"aet-improvement-case-{suffix}.svg",
        )
        if args.frames is not None:
            directory = args.frames / suffix
            directory.mkdir(parents=True, exist_ok=True)
            for phase in range(1, 7):
                svg = directory / f"{phase:02d}.svg"
                png = directory / f"{phase:02d}.png"
                render_case(language, svg, phase=phase)
                subprocess.run(
                    ["sips", "-s", "format", "png", str(svg), "--out", str(png)],
                    check=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
    _manifest(args.assets)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
