#!/usr/bin/env python3
"""Generate bilingual v1.16 Evidence Atlas architecture and video slides."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import textwrap
from html import escape
from pathlib import Path


BG = "#070a10"
PANEL = "#101722"
TEXT = "#edf4ff"
MUTED = "#94a3b8"
CYAN = "#45d7e8"
GREEN = "#71db9b"
AMBER = "#f3b95f"
RED = "#ef7078"
PURPLE = "#b99aff"


def _start(title: str, width: int = 1600, height: int = 900) -> list[str]:
    return [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
            f'height="{height}" viewBox="0 0 {width} {height}" role="img" '
            f'aria-label="{escape(title)}">'
        ),
        "<defs>",
        (
            '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">'
            '<stop stop-color="#070a10"/><stop offset=".55" stop-color="#0b1220"/>'
            '<stop offset="1" stop-color="#08141b"/></linearGradient>'
        ),
        (
            '<pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">'
            '<path d="M30 0H0V30" fill="none" stroke="#334155" '
            'stroke-opacity=".16"/></pattern>'
        ),
        (
            '<filter id="shadow" x="-30%" y="-30%" width="160%" height="160%">'
            '<feDropShadow dx="0" dy="10" stdDeviation="12" flood-color="#000" '
            'flood-opacity=".4"/></filter>'
        ),
        (
            '<marker id="arrow" markerWidth="10" markerHeight="8" refX="9" '
            'refY="4" orient="auto"><path d="M0 0L10 4L0 8Z" '
            f'fill="{CYAN}"/></marker>'
        ),
        (
            '<style>text{font-family:Inter,-apple-system,BlinkMacSystemFont,'
            '"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}'
            '.mono{font-family:"SFMono-Regular",Consolas,monospace}</style>'
        ),
        "</defs>",
        f'<rect width="{width}" height="{height}" fill="url(#bg)"/>',
        f'<rect width="{width}" height="{height}" fill="url(#grid)"/>',
    ]


def _card(
    out: list[str],
    x: int,
    y: int,
    width: int,
    height: int,
    accent: str,
    title: str,
    body: str,
    label: str = "",
) -> None:
    body_lines = textwrap.wrap(
        body,
        width=max(18, (width - 48) // 7),
        break_long_words=True,
        break_on_hyphens=False,
    )[:2]
    out.extend(
        [
            (
                f'<g filter="url(#shadow)"><rect x="{x}" y="{y}" width="{width}" '
                f'height="{height}" rx="18" fill="{PANEL}" fill-opacity=".94" '
                f'stroke="{accent}" stroke-opacity=".42"/>'
            ),
            (
                f'<rect x="{x}" y="{y}" width="5" height="{height}" rx="2.5" '
                f'fill="{accent}"/>'
            ),
            (
                f'<text x="{x + 24}" y="{y + 38}" font-size="20" '
                f'font-weight="700" fill="{TEXT}">{escape(title)}</text>'
            ),
        ]
    )
    for index, line in enumerate(body_lines):
        out.append(
            f'<text x="{x + 24}" y="{y + 68 + index * 20}" '
            f'font-size="14" fill="{MUTED}">{escape(line)}</text>'
        )
    if label:
        out.append(
            f'<text class="mono" x="{x + 24}" y="{y + height - 18}" '
            f'font-size="12" fill="{accent}">{escape(label)}</text>'
        )
    out.append("</g>")


def _arrow(out: list[str], path: str, dashed: bool = False) -> None:
    dash = ' stroke-dasharray="8 8"' if dashed else ""
    out.append(
        f'<path d="{path}" fill="none" stroke="{CYAN}" stroke-width="2.5"'
        f'{dash} marker-end="url(#arrow)"/>'
    )


def architecture(language: str, destination: Path) -> None:
    zh = language == "zh-CN"
    title = "AET v1.16 证据图谱架构" if zh else "AET v1.16 Evidence Atlas Architecture"
    subtitle = (
        "同一份可移植证据，同时形成可递归图谱与有边界的代码改进提示词"
        if zh
        else "One portable evidence source drives a recursive map and bounded code-improvement prompts"
    )
    names = (
        {
            "bundle": ("Portable Evidence Bundle", "Claims · Evidence · Observations · Conflicts"),
            "graph": ("规范化证据图", "来源节点 · 有依据的边 · 权限与时效"),
            "views": ("十个固定视角", "八个证据视角 + Improvement Chain + Regression Lineage"),
            "recursive": ("递归分解", "复杂节点进入子图；叶节点保持简洁"),
            "render": ("确定性投影", "Diagram IR · Mermaid · Markdown · JSON"),
            "viewer": ("离线 Viewer", "三栏浏览 · 路径高亮 · 筛选 · 原始引用"),
            "validate": ("Fail-closed Validator", "反证保留 · stale 不升级 · UNKNOWN 可见"),
            "consume": ("人类与 Agent 审查", "图谱 + 改进报告 + 有边界的 Agent 提示词"),
        }
        if zh
        else {
            "bundle": ("Portable Evidence Bundle", "Claims · Evidence · Observations · Conflicts"),
            "graph": ("Canonical Evidence Graph", "source nodes · grounded edges · authority · Freshness"),
            "views": ("Ten fixed Perspectives", "eight evidence views + Improvement Chain + Regression Lineage"),
            "recursive": ("Recursive decomposition", "complex nodes get subgraphs; leaves stay compact"),
            "render": ("Deterministic projections", "Diagram IR · Mermaid · Markdown · JSON"),
            "viewer": ("Offline Viewer", "three columns · path highlighting · filters · raw refs"),
            "validate": ("Fail-closed Validator", "counter-evidence retained · stale not upgraded · UNKNOWN visible"),
            "consume": ("Human and Agent review", "graph + human report + bounded Agent prompt"),
        }
    )
    out = _start(title)
    out.extend(
        [
            f'<text x="60" y="65" font-size="36" font-weight="800" fill="{TEXT}">{escape(title)}</text>',
            f'<text x="60" y="98" font-size="16" fill="{MUTED}">{escape(subtitle)}</text>',
            f'<text x="1540" y="66" text-anchor="end" class="mono" font-size="13" fill="{GREEN}">DETERMINISTIC · OFFLINE · STRICT</text>',
        ]
    )
    positions = {
        "bundle": (70, 165, 310, 118, CYAN),
        "graph": (465, 165, 310, 118, GREEN),
        "views": (860, 165, 310, 118, PURPLE),
        "recursive": (1255, 165, 280, 118, AMBER),
        "render": (1255, 390, 280, 118, CYAN),
        "viewer": (860, 390, 310, 118, GREEN),
        "validate": (465, 390, 310, 118, RED),
        "consume": (70, 390, 310, 118, AMBER),
    }
    for key, (x, y, width, height, accent) in positions.items():
        item_title, body = names[key]
        _card(out, x, y, width, height, accent, item_title, body)
    _arrow(out, "M380 224H465")
    _arrow(out, "M775 224H860")
    _arrow(out, "M1170 224H1255")
    _arrow(out, "M1395 283V390")
    _arrow(out, "M1255 449H1170")
    _arrow(out, "M860 449H775")
    _arrow(out, "M465 449H380")
    _arrow(out, "M620 390V315H1020V283", dashed=True)
    out.extend(
        [
            (
                f'<rect x="70" y="610" width="1465" height="180" rx="22" '
                f'fill="#ffffff" fill-opacity=".025" stroke="{AMBER}" '
                'stroke-opacity=".4" stroke-dasharray="8 8"/>'
            ),
            f'<text x="105" y="655" font-size="18" font-weight="700" fill="{AMBER}">{escape("权威边界" if zh else "AUTHORITY BOUNDARY")}</text>',
            (
                f'<text x="105" y="700" font-size="24" font-weight="700" fill="{TEXT}">'
                f'{escape("Bundle → Graph / Atlas；Bundle → Issue / Constraint / Prompt" if zh else "Bundle → Graph / Atlas; Bundle → Issue / Constraint / Prompt")}</text>'
            ),
            (
                f'<text x="105" y="746" font-size="17" fill="{MUTED}">'
                f'{escape("两条派生链共享 Evidence ID，但提示词不会回写成证据；最终 Fix、Merge、Push、Release 仍由人决定。" if zh else "Both derivations share Evidence IDs, but prompts never write back as evidence; fix, merge, push, and release remain human decisions.")}</text>'
            ),
            "</svg>",
        ]
    )
    destination.write_text("\n".join(out), encoding="utf-8")


def slides(language: str, directory: Path) -> None:
    zh = language == "zh-CN"
    directory.mkdir(parents=True, exist_ok=True)
    scenes = (
        [
            ("证据文件很多，人类仍难看懂", "Bundle 是权威来源，但关系仍然分散", "01"),
            ("先建规范化 Evidence Graph", "每个节点和边都保留字段级来源引用", "02"),
            ("同一份证据，十个调查视角", "八个证据视角，加上 Improvement Chain 与 Regression Lineage", "03"),
            ("复杂节点递归下钻", "确定性复杂度、深度预算、去重和循环阻断", "04"),
            ("提示词与图谱是同源的两条派生链", "共享 Evidence ID；提示词绝不回写成证据", "05"),
            ("审查更直观，权威边界不变", "无 LLM 也完整可用；人类仍拥有最终行动权限", "06"),
        ]
        if zh
        else [
            ("Evidence is portable—but relationships stay hard to read.", "The Bundle is authoritative; its links are still distributed.", "01"),
            ("Build a canonical Evidence Graph first.", "Every authoritative node and edge keeps field-level source references.", "02"),
            ("One evidence source. Ten investigation views.", "Eight evidence views plus Improvement Chain and Regression Lineage.", "03"),
            ("Drill into complex nodes recursively.", "Deterministic complexity, depth budgets, deduplication, and cycle stops.", "04"),
            ("Prompts and graphs are sibling derivations.", "They share Evidence IDs; prompts never write back as evidence.", "05"),
            ("Readable review. Unchanged authority boundary.", "Complete without an LLM; final action remains human-owned.", "06"),
        ]
    )
    accents = [CYAN, GREEN, PURPLE, AMBER, RED, GREEN]
    for index, (title, body, number) in enumerate(scenes):
        out = _start(title)
        accent = accents[index]
        out.extend(
            [
                f'<text x="90" y="90" class="mono" font-size="16" font-weight="700" fill="{accent}">AET EVIDENCE ATLAS · v1.16</text>',
                f'<text x="1510" y="90" text-anchor="end" class="mono" font-size="16" fill="{MUTED}">{number} / 06</text>',
                f'<text x="90" y="210" font-size="48" font-weight="800" fill="{TEXT}">{escape(title)}</text>',
                f'<text x="90" y="260" font-size="22" fill="{MUTED}">{escape(body)}</text>',
            ]
        )
        if index == 0:
            for idx, label in enumerate(("claims.jsonl", "evidence.jsonl", "conflicts.jsonl", "ledger.jsonl")):
                _card(out, 90 + idx * 360, 380, 315, 135, accents[idx], label, "source-backed records")
        elif index == 1:
            _card(out, 140, 375, 360, 140, CYAN, "Bundle Records", "authoritative source")
            _card(out, 620, 375, 360, 140, GREEN, "Canonical Graph", "stable Node / Edge schema")
            _card(out, 1100, 375, 360, 140, AMBER, "Provenance", "field-level source_refs")
            _arrow(out, "M500 445H620")
            _arrow(out, "M980 445H1100")
        elif index == 2:
            labels = ["Claim", "Flow", "Scope", "Proof", "Data", "Integration", "Conflict", "Freshness", "Improvement", "Regression"]
            for idx, label in enumerate(labels):
                x = 70 + (idx % 5) * 305
                y = 350 + (idx // 5) * 175
                _card(out, x, y, 275, 125, accents[idx % len(accents)], label, "deterministic projection")
        elif index == 3:
            _card(out, 130, 370, 350, 150, CYAN, "Finding", "mandatory decomposition")
            _card(out, 625, 320, 350, 150, GREEN, "Claim", "expandable")
            _card(out, 1120, 270, 350, 150, AMBER, "Proof", "leaf / reference")
            _arrow(out, "M480 445H625")
            _arrow(out, "M975 395H1120")
        elif index == 4:
            _card(out, 105, 360, 410, 165, CYAN, "Human Report", "impact · evidence · scope · verification")
            _card(out, 595, 360, 410, 165, PURPLE, "Agent Prompt", "PROPOSED · bounded · stop conditions")
            _card(out, 1085, 360, 410, 165, GREEN, "Evidence Atlas", "same refs · counter-evidence · UNKNOWN")
        else:
            _card(out, 160, 360, 420, 165, GREEN, "No LLM required", "deterministic build and validation")
            _card(out, 590, 360, 420, 165, CYAN, "Portable", "HTML · Mermaid · Markdown · JSON")
            _card(out, 1020, 360, 420, 165, AMBER, "Human authority", "review, fix, merge, push, release")
        out.extend(
            [
                f'<text x="90" y="842" font-size="16" fill="{MUTED}">{escape("AET v1.16 · 同源审查产物，但不升级证据权限" if zh else "AET v1.16 · sibling review artifacts without authority inflation")}</text>',
                "</svg>",
            ]
        )
        svg = directory / f"{index + 1:02d}.svg"
        png = directory / f"{index + 1:02d}.png"
        svg.write_text("\n".join(out), encoding="utf-8")
        subprocess.run(
            ["sips", "-s", "format", "png", str(svg), "--out", str(png)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", required=True, type=Path)
    parser.add_argument("--slides", type=Path)
    args = parser.parse_args()
    args.assets.mkdir(parents=True, exist_ok=True)
    for language, suffix in (("en", "en"), ("zh-CN", "zh-CN")):
        svg = args.assets / f"aet-evidence-atlas-architecture-{suffix}.svg"
        png = args.assets / f"aet-evidence-atlas-architecture-{suffix}.png"
        architecture(language, svg)
        subprocess.run(
            ["sips", "-s", "format", "png", str(svg), "--out", str(png)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if args.slides is not None:
            slides(language, args.slides / suffix)
    media_names = [
        "aet-evidence-atlas-architecture-en.png",
        "aet-evidence-atlas-architecture-en.svg",
        "aet-evidence-atlas-architecture-zh-CN.png",
        "aet-evidence-atlas-architecture-zh-CN.svg",
        "aet-evidence-atlas-intro-en.mp4",
        "aet-evidence-atlas-intro-zh-CN.mp4",
        "aet-evidence-atlas-viewer.gif",
    ]
    media = []
    for name in media_names:
        path = args.assets / name
        if not path.is_file():
            continue
        media.append(
            {
                "path": f"docs/assets/{name}",
                "bytes": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    manifest = {
        "schema": "aet-readme-media/1.0",
        "release": "v1.16.0",
        "example": {
            "bundle_id": "bundle-aet-atlas-self-review-v1",
            "builder": "examples/evidence-atlas/build_example.py",
            "viewer_capture": "six real offline Viewer states",
        },
        "motion": {
            "gif": {"frames": 6, "frame_seconds": 1.35, "size": "1920x858"},
            "videos": {"duration_seconds": 30, "codec": "H.264", "size": "1600x900"},
        },
        "media": media,
    }
    (args.assets / "aet-evidence-atlas-media-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
