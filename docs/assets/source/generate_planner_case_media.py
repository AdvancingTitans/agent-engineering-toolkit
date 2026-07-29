#!/usr/bin/env python3
"""Generate bilingual real-case comparison screenshots for the README."""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path


INK = "#111827"
MUTED = "#6b7280"
LINE = "#d1d5db"
BLUE = "#2563eb"
PURPLE = "#7c3aed"
GREEN = "#059669"
AMBER = "#d97706"
RED = "#dc2626"


def _start(title: str) -> list[str]:
    return [
        (
            '<svg xmlns="http://www.w3.org/2000/svg" width="1600" '
            'height="900" viewBox="0 0 1600 900" role="img" '
            f'aria-label="{escape(title)}" data-generator="fireworks-tech-graph" '
            'data-schema-version="1" data-style-id="1" '
            'data-visual-theme="Flat Icon" '
            'data-diagram-type="comparison" data-semantic-profile="generic" '
            'data-semantic-valid="true" data-quality-profile="showcase">'
        ),
        "<defs>",
        (
            '<filter id="shadow" x="-20%" y="-20%" width="140%" height="140%">'
            '<feDropShadow dx="0" dy="6" stdDeviation="8" '
            'flood-color="#0f172a" flood-opacity=".08"/></filter>'
        ),
        (
            '<style>text{font-family:"Helvetica Neue",Helvetica,Arial,'
            '"PingFang SC","Microsoft YaHei",sans-serif}'
            '.mono{font-family:"SFMono-Regular",Consolas,monospace}</style>'
        ),
        "</defs>",
        '<rect width="1600" height="900" fill="#ffffff"/>',
        '<rect width="1600" height="98" fill="#f8fafc"/>',
    ]


def _text(
    lines: list[str],
    x: int,
    y: int,
    value: str,
    *,
    size: int = 16,
    color: str = INK,
    weight: int = 400,
    anchor: str = "start",
    mono: bool = False,
) -> None:
    klass = ' class="mono"' if mono else ""
    lines.append(
        f'<text x="{x}" y="{y}" text-anchor="{anchor}"{klass} '
        f'font-size="{size}" font-weight="{weight}" fill="{color}">'
        f"{escape(value)}</text>"
    )


def _pill(
    lines: list[str],
    x: int,
    y: int,
    width: int,
    value: str,
    color: str,
) -> None:
    lines.append(
        f'<rect x="{x}" y="{y}" width="{width}" height="30" rx="15" '
        f'fill="{color}" fill-opacity=".10" stroke="{color}" '
        'stroke-opacity=".45"/>'
    )
    _text(
        lines,
        x + width // 2,
        y + 20,
        value,
        size=12,
        color=color,
        weight=750,
        anchor="middle",
        mono=True,
    )


def _column(
    lines: list[str],
    *,
    x: int,
    title: str,
    subtitle: str,
    color: str,
    metrics: list[tuple[str, str, str]],
    decisions: list[str],
) -> None:
    lines.extend(
        [
            f'<g filter="url(#shadow)">',
            f'<rect x="{x}" y="250" width="450" height="535" rx="18" '
            f'fill="#ffffff" stroke="{color}" stroke-width="2"/>',
            f'<rect x="{x}" y="250" width="450" height="86" rx="18" '
            f'fill="{color}" fill-opacity=".08"/>',
            "</g>",
        ]
    )
    _text(lines, x + 28, 285, title, size=24, weight=800, color=color)
    _text(lines, x + 28, 316, subtitle, size=14, color=MUTED)
    for index, (label, value, status) in enumerate(metrics):
        y = 376 + index * 48
        if index % 2:
            lines.append(
                f'<rect x="{x + 20}" y="{y - 27}" width="410" height="39" '
                'rx="7" fill="#f8fafc"/>'
            )
        _text(lines, x + 30, y, label, size=14, color=MUTED)
        status_color = {
            "good": GREEN,
            "warn": AMBER,
            "bad": RED,
        }[status]
        _text(
            lines,
            x + 416,
            y,
            value,
            size=17,
            color=status_color,
            weight=800,
            anchor="end",
            mono=True,
        )
    lines.append(
        f'<line x1="{x + 24}" y1="625" x2="{x + 426}" y2="625" '
        f'stroke="{LINE}"/>'
    )
    _text(lines, x + 28, 655, "Scope decisions", size=13, color=color, weight=750)
    for index, decision in enumerate(decisions):
        _text(
            lines,
            x + 30,
            685 + index * 27,
            decision,
            size=13,
            color=INK,
            mono=True,
        )


def render(language: str, output: Path) -> None:
    zh = language == "zh-CN"
    title = (
        "真实 AET 项目：有计划与没计划，修改范围判断差多少？"
        if zh
        else "Real AET repository: how much does a Plan change scope judgment?"
    )
    subtitle = (
        "同一 gpt-5.6-sol / medium / 只读任务；逐维评分，不生成单一 Trust Score"
        if zh
        else "Same gpt-5.6-sol / medium / read-only task; dimension-level metrics, never one trust score"
    )
    request = (
        "“规划 Graph Builder、固定 Perspective、递归 Viewer 与 Bundle v1 Change Group 兼容改动。”"
        if zh
        else "“Plan a Graph Builder, fixed Perspective, recursive Viewer, and Bundle v1 Change Group compatibility change.”"
    )
    labels = (
        ["生产决策精确率", "Disposition 正确率", "必需测试召回", "证据引用覆盖", "联动覆盖", "UNKNOWN 保留"]
        if zh
        else ["Production precision", "Disposition accuracy", "Required-test recall", "Evidence-ref coverage", "Linkage coverage", "UNKNOWN preservation"]
    )
    lines = _start(title)
    _text(lines, 58, 45, title, size=30, weight=850)
    _text(lines, 58, 75, subtitle, size=15, color=MUTED)
    _pill(lines, 1278, 34, 264, "ONE REAL CASE · PASS@1", GREEN)
    lines.append(
        '<rect x="58" y="125" width="1484" height="82" rx="14" '
        'fill="#eff6ff" stroke="#93c5fd"/>'
    )
    _text(lines, 86, 156, "DEVELOPER" if not zh else "开发者", size=13, color=BLUE, weight=800, mono=True)
    _text(lines, 86, 187, request, size=18, color=INK, weight=650)
    common = [
        (labels[0], "44.4%", "bad"),
        (labels[1], "75%", "warn"),
        (labels[2], "100%", "good"),
        (labels[3], "0%", "bad"),
        (labels[4], "33.3%", "bad"),
        (labels[5], "0%", "bad"),
    ]
    evidence = [
        (labels[0], "100%", "good"),
        (labels[1], "50%", "bad"),
        (labels[2], "0%", "bad"),
        (labels[3], "100%", "good"),
        (labels[4], "100%", "good"),
        (labels[5], "50%", "warn"),
    ]
    planned = [
        (labels[0], "100%", "good"),
        (labels[1], "100%", "good"),
        (labels[2], "100%", "good"),
        (labels[3], "100%", "good"),
        (labels[4], "100%", "good"),
        (labels[5], "100%", "good"),
    ]
    _column(
        lines,
        x=58,
        title="Source only" if not zh else "只看源码",
        subtitle="9 production decisions · no evidence refs" if not zh else "9 个生产决策 · 无证据引用",
        color=BLUE,
        metrics=common,
        decisions=[
            "builder.py           REQUIRED",
            "viewer.py            REQUIRED",
            "+ validator / hierarchy / model / schemas",
        ],
    )
    _column(
        lines,
        x=575,
        title="v1.16 evidence-only",
        subtitle="Bundle + Atlas · no Planning Context" if not zh else "Bundle + Atlas · 没有 Planning Context",
        color=PURPLE,
        metrics=evidence,
        decisions=[
            "builder.py           REQUIRED",
            "viewer.py            INVESTIGATE",
            "evidence.schema.json DO_NOT_EDIT · tests missing",
        ],
    )
    _column(
        lines,
        x=1092,
        title="v1.17 validated Plan",
        subtitle="PROPOSED package → Code Agent Planner" if not zh else "PROPOSED Plan → Code Agent Planner",
        color=GREEN,
        metrics=planned,
        decisions=[
            "builder.py           REQUIRED · ev-graph-builder",
            "viewer.py            REQUIRED · ev-viewer",
            "evidence.schema.json INVESTIGATE · conflict + UNKNOWN",
        ],
    )
    lines.extend(
        [
            '<rect x="58" y="824" width="1484" height="48" rx="12" fill="#111827"/>',
        ]
    )
    boundary = (
        "结论边界：1 个真实仓库 case、每组 1 次；召回没有提升，提升发生在精确率、类型、联动、验证与 UNKNOWN 保留。"
        if zh
        else "Boundary: one real repository case, one run per group. Recall did not improve; precision, disposition, linkage, tests, and UNKNOWN did."
    )
    _text(lines, 800, 854, boundary, size=14, color="#ffffff", weight=650, anchor="middle")
    lines.append("</svg>")
    output.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", required=True, type=Path)
    args = parser.parse_args()
    args.assets.mkdir(parents=True, exist_ok=True)
    render("en", args.assets / "aet-planner-real-case-en.svg")
    render("zh-CN", args.assets / "aet-planner-real-case-zh-CN.svg")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
