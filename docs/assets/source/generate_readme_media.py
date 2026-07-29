#!/usr/bin/env python3
"""Generate bilingual README panorama and temporary product-video slides."""

from __future__ import annotations

import argparse
from html import escape
from pathlib import Path


BG = "#070a12"
PANEL = "#111827"
TEXT = "#f8fafc"
MUTED = "#94a3b8"
BLUE = "#60a5fa"
PURPLE = "#c084fc"
GREEN = "#34d399"
AMBER = "#f59e0b"


def _svg_start(width: int, height: int, title: str) -> list[str]:
    return [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
        "<defs>",
        '<linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#070a12"/><stop offset=".55" stop-color="#0d1324"/><stop offset="1" stop-color="#07111c"/></linearGradient>',
        '<radialGradient id="blueGlow"><stop stop-color="#2563eb" stop-opacity=".20"/><stop offset="1" stop-color="#2563eb" stop-opacity="0"/></radialGradient>',
        '<radialGradient id="purpleGlow"><stop stop-color="#7c3aed" stop-opacity=".16"/><stop offset="1" stop-color="#7c3aed" stop-opacity="0"/></radialGradient>',
        '<pattern id="grid" width="32" height="32" patternUnits="userSpaceOnUse"><path d="M32 0H0V32" fill="none" stroke="#334155" stroke-opacity=".18"/></pattern>',
        '<filter id="shadow" x="-30%" y="-30%" width="160%" height="160%"><feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#000" flood-opacity=".35"/></filter>',
        '<filter id="softGlow" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="5" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>',
        '<marker id="arrowBlue" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0 0L10 4L0 8Z" fill="#60a5fa"/></marker>',
        '<marker id="arrowPurple" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0 0L10 4L0 8Z" fill="#c084fc"/></marker>',
        '<marker id="arrowGreen" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0 0L10 4L0 8Z" fill="#34d399"/></marker>',
        '<marker id="arrowAmber" markerWidth="10" markerHeight="8" refX="9" refY="4" orient="auto"><path d="M0 0L10 4L0 8Z" fill="#f59e0b"/></marker>',
        '<style>text{font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif}.mono{font-family:"SFMono-Regular",Consolas,"Liberation Mono",monospace}</style>',
        "</defs>",
        f'<rect width="{width}" height="{height}" fill="url(#bg)"/>',
        f'<circle data-graph-role="decoration" data-owner="canvas" cx="{width * .18:.0f}" cy="{height * .25:.0f}" r="{width * .32:.0f}" fill="url(#blueGlow)"/>',
        f'<circle data-graph-role="decoration" data-owner="canvas" cx="{width * .82:.0f}" cy="{height * .55:.0f}" r="{width * .28:.0f}" fill="url(#purpleGlow)"/>',
        f'<rect width="{width}" height="{height}" fill="url(#grid)"/>',
    ]


def _card(
    lines: list[str],
    x: int,
    y: int,
    width: int,
    height: int,
    accent: str,
    title: str,
    subtitle: str,
    path: str = "",
) -> None:
    lines.extend(
        [
            f'<g filter="url(#shadow)">',
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="18" fill="{PANEL}" fill-opacity=".86" stroke="#ffffff" stroke-opacity=".12"/>',
            f'<rect x="{x}" y="{y}" width="5" height="{height}" rx="2.5" fill="{accent}"/>',
            f'<text x="{x + 24}" y="{y + 34}" font-size="19" font-weight="700" fill="{TEXT}">{escape(title)}</text>',
            f'<text x="{x + 24}" y="{y + 61}" font-size="14" fill="{MUTED}">{escape(subtitle)}</text>',
        ]
    )
    if path:
        lines.append(
            f'<text class="mono" x="{x + 24}" y="{y + height - 16}" font-size="12" fill="{accent}">{escape(path)}</text>'
        )
    lines.append("</g>")


def _section(lines: list[str], x: int, y: int, width: int, height: int, index: str, title: str, accent: str) -> None:
    lines.extend(
        [
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="24" fill="#ffffff" fill-opacity=".025" stroke="{accent}" stroke-opacity=".32" stroke-dasharray="7 8"/>',
            f'<circle cx="{x + 30}" cy="{y + 28}" r="16" fill="{accent}" fill-opacity=".18" stroke="{accent}"/>',
            f'<text x="{x + 30}" y="{y + 34}" text-anchor="middle" font-size="13" font-weight="800" fill="{accent}">{escape(index)}</text>',
            f'<text x="{x + 58}" y="{y + 35}" font-size="18" font-weight="750" fill="{TEXT}">{escape(title)}</text>',
        ]
    )


def _arrow(lines: list[str], path: str, color: str, marker: str, dashed: bool = False) -> None:
    dash = ' stroke-dasharray="8 8"' if dashed else ""
    lines.append(
        f'<path d="{path}" fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"{dash} marker-end="url(#{marker})"/>'
    )


def render_panorama(language: str, output: Path) -> None:
    zh = language == "zh-CN"
    title = "AET v1.17 项目架构全景" if zh else "AET v1.17 Project Architecture Panorama"
    subtitle = (
        "从 Agent 运行记录到可移植证据、Evidence Atlas、改进提示词与只读计划；权威始终分层"
        if zh
        else "From Agent runs to portable evidence, Atlas, improvement prompts, and read-only Plans—with authority kept separate"
    )
    section_titles = (
        ("采集与标准化", "有边界的调查与验证", "证据派生的审查产物", "产品入口与治理")
        if zh
        else ("Capture and normalization", "Bounded investigation and verification", "Evidence-derived review artifacts", "Product surfaces and governance")
    )
    cards = {
        "skills": ("原生 Agent 运行记录", "Codex · Claude Code · JSONL", "") if zh else ("Native Agent runs", "Codex · Claude Code · JSONL", ""),
        "cli": ("Source Adapter", "解析消息、工具调用与工具结果", "run_normalization/adapters/*") if zh else ("Source adapters", "messages · tool calls · tool results", "run_normalization/adapters/*"),
        "host": ("Run Normalizer", "稳定身份 · 增量导入 · Diagnostics", "src/aet/run_normalization/*") if zh else ("Run Normalizer", "stable IDs · incremental ingest · diagnostics", "src/aet/run_normalization/*"),
        "human": ("Canonical Run Record", "运行记录只证明记录中发生了什么", "schemas/run-record/v1/*") if zh else ("Canonical Run Records", "records prove only what the run contains", "schemas/run-record/v1/*"),
        "handlers": ("Observation", "强制声明 proves / doesNotProve", "src/aet/observations/*") if zh else ("Observations", "explicit proves / doesNotProve", "src/aet/observations/*"),
        "investigate": ("Evidence Candidate", "待验证 · 可拒绝 · 可冲突", "src/aet/evidence_core/*") if zh else ("Evidence Candidates", "unverified · rejected · conflicted", "src/aet/evidence_core/*"),
        "ledger": ("只读 Investigator", "主假设 · 竞争假设 · 停止条件", "investigation/portable.py") if zh else ("Read-only Investigator", "primary · competing · stop conditions", "investigation/portable.py"),
        "validator": ("确定性证据权威", "Git · Proof · Freshness · 权限", "quick/* · grounding.py") if zh else ("Deterministic authority", "Git · Proof · Freshness · authority", "quick/* · grounding.py"),
        "evidence": ("Bundle Compiler", "筛选 · 脱敏 · 内容寻址", "src/aet/bundle/compiler.py") if zh else ("Bundle Compiler", "select · redact · content-address", "src/aet/bundle/compiler.py"),
        "binding": ("Portable Evidence Bundle", "Claim · Evidence · Observation · Proof", "schemas/evidence-bundle/v1/*") if zh else ("Portable Evidence Bundle", "Claim · Evidence · Observation · Proof", "schemas/evidence-bundle/v1/*"),
        "contracts": ("Evidence Atlas", "十个视角 · 递归图 · UNKNOWN 可见", "src/aet/atlas/*") if zh else ("Evidence Atlas", "ten views · recursive graph · visible UNKNOWN", "src/aet/atlas/*"),
        "quality": ("改进提示词与 PROPOSED Plan", "Issue · Scope · 引用 · 验证 · UNKNOWN", "improvement/* · planning/*") if zh else ("Prompts + PROPOSED Plans", "Issue · scope · refs · tests · UNKNOWN", "improvement/* · planning/*"),
        "showcase": ("四个 Quick Skill", "Check · Scope · Proof · Fresh", "skills/aet-* · src/aet/quick/*") if zh else ("Four Quick Skills", "Check · Scope · Proof · Fresh", "skills/aet-* · src/aet/quick/*"),
        "memory": ("便利接入层", "CLI · MCP · TypeScript / Python SDK", "src/aet/mcp_server.py · packages/*") if zh else ("Convenience integrations", "CLI · MCP · TypeScript / Python SDK", "src/aet/mcp_server.py · packages/*"),
        "learn": ("真实 Atlas 范围对照", "source-only · v1.16 evidence · v1.17 plan", "eval/evidence-guided-planner/*") if zh else ("Real Atlas scope comparison", "source-only · v1.16 evidence · v1.17 plan", "eval/evidence-guided-planner/*"),
        "gate": ("人工决定与 Lab 边界", "不自动 Fix · Merge · Push · Release", "docs/quick-vs-lab-boundary.md") if zh else ("Human decision and Lab", "no automatic fix · merge · push · release", "docs/quick-vs-lab-boundary.md"),
    }
    lines = _svg_start(1600, 1000, title)
    lines.extend(
        [
            f'<text x="60" y="60" font-size="34" font-weight="800" fill="{TEXT}">{escape(title)}</text>',
            f'<text x="60" y="88" font-size="16" fill="{MUTED}">{escape(subtitle)}</text>',
            f'<text x="1540" y="62" text-anchor="end" class="mono" font-size="13" fill="{GREEN}">EVIDENCE → PLAN → HUMAN · v1.17</text>',
        ]
    )
    for args in (
        (40, 115, 1520, 150, "01", section_titles[0], BLUE),
        (40, 295, 1520, 200, "02", section_titles[1], PURPLE),
        (40, 525, 1520, 190, "03", section_titles[2], GREEN),
        (40, 745, 1520, 190, "04", section_titles[3], AMBER),
    ):
        _section(lines, *args)
    positions = {
        "skills": (70, 165, 320, 96, BLUE),
        "cli": (430, 165, 320, 96, PURPLE),
        "host": (790, 165, 320, 96, GREEN),
        "human": (1150, 165, 340, 96, AMBER),
        "handlers": (70, 355, 320, 104, BLUE),
        "investigate": (430, 355, 320, 104, PURPLE),
        "ledger": (790, 355, 320, 104, GREEN),
        "validator": (1150, 355, 340, 104, AMBER),
        "evidence": (70, 585, 320, 98, GREEN),
        "binding": (430, 585, 320, 98, BLUE),
        "contracts": (790, 585, 320, 98, PURPLE),
        "quality": (1150, 585, 340, 98, AMBER),
        "showcase": (70, 825, 320, 88, AMBER),
        "memory": (430, 825, 320, 88, BLUE),
        "learn": (790, 825, 320, 88, PURPLE),
        "gate": (1150, 825, 340, 88, GREEN),
    }
    for key, (x, y, width, height, accent) in positions.items():
        card_title, card_subtitle, card_path = cards[key]
        _card(lines, x, y, width, height, accent, card_title, card_subtitle, card_path)
    _arrow(lines, "M230 261V355", BLUE, "arrowBlue")
    _arrow(lines, "M590 261V355", PURPLE, "arrowPurple")
    _arrow(lines, "M950 261V355", GREEN, "arrowGreen")
    _arrow(lines, "M390 407H430", BLUE, "arrowBlue")
    _arrow(lines, "M750 407H790", PURPLE, "arrowPurple")
    _arrow(lines, "M1110 407H1150", GREEN, "arrowGreen")
    _arrow(lines, "M1320 261V355", AMBER, "arrowAmber")
    _arrow(lines, "M230 459V585", GREEN, "arrowGreen")
    _arrow(lines, "M590 459V585", BLUE, "arrowBlue")
    _arrow(lines, "M950 459V585", PURPLE, "arrowPurple")
    _arrow(lines, "M1320 459V585", AMBER, "arrowAmber")
    lines.extend(
        [
            f'<rect x="1190" y="776" width="260" height="34" rx="17" fill="{AMBER}" fill-opacity=".13" stroke="{AMBER}" stroke-dasharray="6 6"/>',
            f'<text x="1320" y="798" text-anchor="middle" class="mono" font-size="12" font-weight="800" fill="{AMBER}">{escape("人工拥有最终行动权限" if zh else "HUMAN OWNS FINAL ACTION")}</text>',
        ]
    )
    _arrow(lines, "M230 683V825", AMBER, "arrowAmber", True)
    _arrow(lines, "M590 683V825", BLUE, "arrowBlue", True)
    _arrow(lines, "M950 683V825", PURPLE, "arrowPurple", True)
    _arrow(lines, "M1320 683V825", GREEN, "arrowGreen", True)
    lines.extend(
        [
            f'<text x="60" y="962" font-size="14" fill="{MUTED}">{escape("实线：证据生产主链 · 虚线：产品入口与消费层" if zh else "Solid: evidence production · dashed: product and consumption surfaces")}</text>',
            f'<text x="1540" y="962" text-anchor="end" font-size="14" font-weight="700" fill="{TEXT}">{escape("审查者无需安装 AET；最终行动权限始终由人掌握" if zh else "Reviewers need no AET install; final action remains human-owned")}</text>',
            "</svg>",
        ]
    )
    output.write_text("\n".join(lines), encoding="utf-8")


def _slide_base(title: str, kicker: str, number: str) -> list[str]:
    lines = _svg_start(1600, 900, title)
    lines.extend(
        [
            f'<text x="90" y="92" class="mono" font-size="16" font-weight="700" fill="{GREEN}">{escape(kicker)}</text>',
            f'<text x="90" y="158" font-size="48" font-weight="850" fill="{TEXT}">{escape(title)}</text>',
            f'<text x="1510" y="92" text-anchor="end" class="mono" font-size="16" fill="{MUTED}">{escape(number)} / 06</text>',
        ]
    )
    return lines


def _slide_card(lines: list[str], x: int, y: int, width: int, height: int, accent: str, title: str, body: list[str]) -> None:
    lines.extend(
        [
            f'<rect x="{x}" y="{y}" width="{width}" height="{height}" rx="24" fill="{PANEL}" fill-opacity=".88" stroke="{accent}" stroke-opacity=".55" filter="url(#shadow)"/>',
            f'<rect x="{x}" y="{y}" width="{width}" height="5" rx="2.5" fill="{accent}"/>',
            f'<text x="{x + 34}" y="{y + 56}" font-size="25" font-weight="800" fill="{TEXT}">{escape(title)}</text>',
        ]
    )
    for index, row in enumerate(body):
        lines.append(
            f'<text x="{x + 34}" y="{y + 104 + index * 38}" font-size="19" fill="{MUTED}">{escape(row)}</text>'
        )


def render_slides(language: str, output_dir: Path) -> None:
    zh = language == "zh-CN"
    output_dir.mkdir(parents=True, exist_ok=True)
    content = [
        (
            "让 Agent 审查项目，怎样避免一上来就改错范围？" if zh else "You ask an Agent to review a project. How do you prevent scope drift?",
            "DEVELOPER REALITY" if not zh else "现实开发场景",
            [
                ("源码搜索可能扩散到无关模块" if zh else "Source search can fan out into unrelated modules", BLUE),
                ("Evidence 能收敛路径，但未必给出修改关系" if zh else "Evidence narrows paths but may not encode edit relationships", PURPLE),
                ("Code Agent 动手前需要可审查的只读 Plan" if zh else "A code Agent needs a reviewable read-only Plan before editing", AMBER),
            ],
        ),
        (
            "v1.16 提供事实层，v1.17 增加规划交接层" if zh else "v1.16 supplies facts; v1.17 adds the planning handoff.",
            "VERSION RELATIONSHIP",
            [
                ("v1.16 · Bundle + Atlas + Improvement" if zh else "v1.16 · Bundle + Atlas + Improvement", BLUE),
                ("v1.17 · Planning Context + Candidate Validator" if zh else "v1.17 · Planning Context + Candidate Validator", PURPLE),
                ("Plan 权限始终为 PROPOSED" if zh else "Plan authority always remains PROPOSED", GREEN),
                ("Proof 未执行前始终 UNKNOWN / PENDING" if zh else "Proof stays UNKNOWN / PENDING until executed", AMBER),
            ],
        ),
        (
            "把证据编译成 Planner 能消费的有界上下文" if zh else "Compile evidence into bounded context a Planner can consume.",
            "PLANNING CONTEXT",
            [
                ("Request + allowed paths", "HUMAN INTENT", BLUE),
                ("Bundle + Atlas + source SHA", "RECORDED FACTS", GREEN),
                ("Budgets + protected paths", "FAIL-CLOSED BOUNDARY", AMBER),
            ],
        ),
        (
            "Host 负责判断，AET 负责确定性校验" if zh else "The Host judges; AET validates deterministically.",
            "PLANNER BOUNDARY",
            [
                ("Host Candidate", "路径 · disposition · linkage" if zh else "paths · disposition · linkage", BLUE),
                ("AET Validator", "引用 · 哈希 · Scope · Policy" if zh else "refs · hashes · scope · policy", GREEN),
                ("Portable Plan", "源码定位 · 测试 · 风险 · UNKNOWN" if zh else "source locators · tests · risks · UNKNOWN", AMBER),
            ],
        ),
        (
            "把 Plan 接进 Code Agent 的 Planner" if zh else "Connect the Plan to a code Agent's planner.",
            "CODE AGENT HANDOFF",
            [
                ("Plan Package", "plan.json · refs · consumer guide", BLUE),
                ("/aet-plan Skill", "Codex · Claude Code · generic Host", PURPLE),
                ("Code Agent Planner", "只读读取，再由人批准实施" if zh else "reads only; human approves implementation", GREEN),
                ("Verification Handoff", "外部 diff → UNKNOWN / PENDING" if zh else "external diff → UNKNOWN / PENDING", AMBER),
            ],
        ),
        (
            "真实案例：Atlas Change Group 修改范围判断" if zh else "Real case: localizing an Atlas Change Group change.",
            "REPRODUCIBLE CASE" if not zh else "可复现案例",
            [
                ("source-only", "路径精确率 44.4% · disposition 75%" if zh else "precision 44.4% · disposition 75%", BLUE),
                ("v1.16 evidence-only", "路径精确率 100% · 测试召回 0%" if zh else "precision 100% · test recall 0%", PURPLE),
                ("v1.17 Plan", "路径/类型/测试/UNKNOWN 均 100%" if zh else "paths/disposition/tests/UNKNOWN all 100%", GREEN),
                ("样本边界" if zh else "Sample boundary", "1 个真实 case · 非通用质量声明" if zh else "one real case · not a general claim", AMBER),
            ],
        ),
    ]
    for index, (title, kicker, items) in enumerate(content, start=1):
        lines = _slide_base(title, kicker, f"{index:02d}")
        if index in {1, 2}:
            height = 150 if index == 1 else 120
            gap = 26
            start = 245
            for item_index, (text, accent) in enumerate(items):
                y = start + item_index * (height + gap)
                lines.extend(
                    [
                        f'<rect x="90" y="{y}" width="1420" height="{height}" rx="24" fill="{PANEL}" fill-opacity=".86" stroke="{accent}" stroke-opacity=".5" filter="url(#shadow)"/>',
                        f'<circle cx="138" cy="{y + height / 2:.0f}" r="17" fill="{accent}" filter="url(#softGlow)"/>',
                        f'<text x="185" y="{y + height / 2 + 9:.0f}" class="mono" font-size="25" font-weight="750" fill="{TEXT}">{escape(text)}</text>',
                    ]
                )
        elif index == 3:
            y = 275
            for left, right, accent in items:
                lines.extend(
                    [
                        f'<rect x="120" y="{y}" width="1360" height="130" rx="22" fill="{PANEL}" fill-opacity=".88" stroke="{accent}" stroke-opacity=".55"/>',
                        f'<text x="165" y="{y + 78}" class="mono" font-size="27" fill="{TEXT}">{escape(left)}</text>',
                        f'<text x="1435" y="{y + 78}" text-anchor="end" class="mono" font-size="23" font-weight="800" fill="{accent}">{escape(right)}</text>',
                    ]
                )
                y += 155
        else:
            columns = 2
            for item_index, (left, right, accent) in enumerate(items):
                x = 90 + (item_index % columns) * 725
                y = 275 + (item_index // columns) * 250
                _slide_card(lines, x, y, 680, 205, accent, left, [right])
        lines.extend(
            [
                f'<text x="90" y="850" font-size="16" fill="{MUTED}">{escape("AET v1.17 · 从可移植证据到可审查的只读计划" if zh else "AET v1.17 · from portable evidence to a reviewable read-only Plan")}</text>',
                "</svg>",
            ]
        )
        (output_dir / f"{index:02d}.svg").write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--assets", type=Path, required=True)
    parser.add_argument("--slides", type=Path)
    args = parser.parse_args()
    args.assets.mkdir(parents=True, exist_ok=True)
    render_panorama("en", args.assets / "aet-project-panorama-en.svg")
    render_panorama("zh-CN", args.assets / "aet-project-panorama-zh-CN.svg")
    if args.slides:
        render_slides("en", args.slides / "en")
        render_slides("zh-CN", args.slides / "zh-CN")


if __name__ == "__main__":
    main()
