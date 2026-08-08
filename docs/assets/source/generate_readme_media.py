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
    title = "AET v1.19 证据平面全景" if zh else "AET v1.19 Evidence Plane Panorama"
    subtitle = (
        "从人类意图与 Agent 运行，到可移植证据、图优先审查、风险诊断与人工决策"
        if zh
        else "From human intent and Agent runs to portable evidence, graph-first review, diagnosis, and human decisions"
    )
    section_titles = (
        ("意图、运行与标准化", "证据生产与确定性验证", "有界审查与决策辅助", "产品入口、案例与治理")
        if zh
        else ("Intent, runs, and normalization", "Evidence production and verification", "Bounded review and decision support", "Product entrypoints, cases, and governance")
    )
    cards = {
        "skills": ("人类意图与权限", "Scope · protected paths · stop", "aet.intent.json") if zh else ("Human intent and authority", "scope · protected paths · stop", "aet.intent.json"),
        "cli": ("Agent Host 与 Skill", "Codex · Claude Code · CI · MCP", "skills/* · integrations/*") if zh else ("Agent Hosts and Skills", "Codex · Claude Code · CI · MCP", "skills/* · integrations/*"),
        "host": ("Run Normalizer", "稳定身份 · 工具调用 · Diagnostics", "src/aet/run_normalization/*") if zh else ("Run Normalizer", "stable IDs · tool calls · diagnostics", "src/aet/run_normalization/*"),
        "human": ("Canonical Records", "只证明记录中发生了什么", "schemas/run-record/v1/*") if zh else ("Canonical Records", "prove only what records contain", "schemas/run-record/v1/*"),
        "handlers": ("Quick + Intent Gate", "Check · Scope · Proof · Fresh", "src/aet/quick/*") if zh else ("Quick + Intent Gate", "Check · Scope · Proof · Fresh", "src/aet/quick/*"),
        "investigate": ("只读 Investigator", "竞争假设 · 预算 · 停止条件", "src/aet/investigation/*") if zh else ("Read-only Investigator", "competing hypotheses · budgets · stops", "src/aet/investigation/*"),
        "ledger": ("确定性证据权威", "Git · Proof · Freshness · 来源", "src/aet/grounding.py") if zh else ("Deterministic authority", "Git · Proof · Freshness · provenance", "src/aet/grounding.py"),
        "validator": ("Portable Evidence Bundle", "内容寻址 · 脱敏 · 可移植", "src/aet/bundle/*") if zh else ("Portable Evidence Bundle", "content-addressed · redacted · portable", "src/aet/bundle/*"),
        "evidence": ("Evidence Atlas", "11 个视角 · 冲突 · UNKNOWN", "src/aet/atlas/*") if zh else ("Evidence Atlas", "11 views · conflicts · visible UNKNOWN", "src/aet/atlas/*"),
        "binding": ("Improvement + Plan", "Issue · refs · tests · PROPOSED", "improvement/* · planning/*") if zh else ("Improvement + Plan", "issues · refs · tests · PROPOSED", "improvement/* · planning/*"),
        "contracts": ("Review Graph", "代码 + 证据 + 权限 · 按需展开", "src/aet/review_graph/*") if zh else ("Review Graph", "code + evidence + authority · expand", "src/aet/review_graph/*"),
        "quality": ("Behavioural Risk", "3 个可观察因素 · 诊断而非预测", "src/aet/risk/*") if zh else ("Behavioural Risk", "3 observable factors · not prediction", "src/aet/risk/*"),
        "showcase": ("CLI · MCP · SDK", "自描述产物优先，接入层可选", "src/aet/cli.py · packages/*") if zh else ("CLI · MCP · SDK", "artifacts first; integrations optional", "src/aet/cli.py · packages/*"),
        "memory": ("可复现案例库", "Stale · Scope · Review · Risk · Plan", "examples/* · docs/use-cases/*") if zh else ("Reproducible case library", "Stale · Scope · Review · Risk · Plan", "examples/* · docs/use-cases/*"),
        "learn": ("确定性 Release 门禁", "Schema · tests · Wheel · diff binding", ".github/workflows/*") if zh else ("Deterministic Release gates", "Schemas · tests · Wheel · diff binding", ".github/workflows/*"),
        "gate": ("人工最终决策", "不自动 Fix · Merge · Push · Release", "docs/quick-vs-lab-boundary.md") if zh else ("Human final decision", "no automatic fix · merge · push · release", "docs/quick-vs-lab-boundary.md"),
    }
    lines = _svg_start(1600, 1000, title)
    lines.extend(
        [
            f'<text x="60" y="60" font-size="34" font-weight="800" fill="{TEXT}">{escape(title)}</text>',
            f'<text x="60" y="88" font-size="16" fill="{MUTED}">{escape(subtitle)}</text>',
            f'<text x="1540" y="62" text-anchor="end" class="mono" font-size="13" fill="{GREEN}">INTENT → EVIDENCE → REVIEW → HUMAN · v1.19</text>',
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
            "Agent 说“完成”时，证据在哪里？" if zh else "When an Agent says “done,” where is the evidence?",
            "THE MISSING PLANE" if not zh else "缺失的一层",
            [
                ("测试通过，不等于证明仍适用于当前源码" if zh else "A passing test may no longer apply to current source", BLUE),
                ("代码关系，不等于修改权限或可信结论" if zh else "Code relationships do not grant edit authority", PURPLE),
                ("Agent 叙述，不会自动升级为 Evidence" if zh else "Agent narration never promotes itself to Evidence", AMBER),
            ],
        ),
        (
            "AET 是编码 Agent 的本地 Evidence Plane" if zh else "AET is a local Evidence Plane for coding Agents.",
            "AET v1.19",
            [
                ("人类 Intent + Agent 运行 + Git 快照" if zh else "Human intent + Agent runs + Git snapshots", BLUE),
                ("哈希绑定的 Proof + Freshness + Bundle" if zh else "Hash-bound Proof + Freshness + Bundle", PURPLE),
                ("Atlas + Review Graph + Risk + Plan" if zh else "Atlas + Review Graph + Risk + Plan", GREEN),
                ("最终行动权限始终属于人" if zh else "Final action authority always remains human", AMBER),
            ],
        ),
        (
            "默认先读最小、可追溯的审查切片" if zh else "Start review with a minimal, traceable slice.",
            "GRAPH-FIRST REVIEW" if not zh else "图优先审查",
            [
                ("root.slice.json", "代码 + Evidence + Scope" if zh else "CODE + EVIDENCE + SCOPE", BLUE),
                ("按需 expand 一跳" if zh else "Expand one hop on demand", "不先吞整个图或仓库" if zh else "DO NOT READ THE WHOLE GRAPH", GREEN),
                ("快照漂移" if zh else "Snapshot drift", "UNKNOWN + STOP + REBUILD", AMBER),
            ],
        ),
        (
            "行为风险诊断只陈述可观察证据" if zh else "Behavioural diagnosis stays with observable evidence.",
            "DIAGNOSIS, NOT MIND READING" if not zh else "诊断，不读心",
            [
                ("Goal divergence", "相对显式 Intent" if zh else "relative to explicit intent", BLUE),
                ("Harm capability", "当前权限下已证明" if zh else "proven in current permissions", PURPLE),
                ("Oversight resistance", "需要观察到行动和效果" if zh else "requires observed action + effect", GREEN),
                ("Interventions", "始终 PROPOSED" if zh else "always PROPOSED", AMBER),
            ],
        ),
        (
            "每天只选择回答当前问题的能力面" if zh else "Choose only the surface that answers today's question.",
            "BOUNDED WORKFLOW" if not zh else "有界工作流",
            [
                ("Quick", "Check · Scope · Proof · Fresh", BLUE),
                ("Evidence", "Bundle · Atlas · Investigation", PURPLE),
                ("Review", "Improvement · Plan · Review Graph", GREEN),
                ("Lab", "Risk · Learn · Archaeologist", AMBER),
            ],
        ),
        (
            "可复现案例，明确边界，不编造总分" if zh else "Reproducible cases, explicit limits, no trust score.",
            "PROVE THE BOUNDARY" if not zh else "证明边界",
            [
                ("Stale Proof", "PASS → changed source → stale", BLUE),
                ("Review Graph", "单个冻结案例减少 23.2%" if zh else "23.2% less in one frozen case", PURPLE),
                ("Planner", "有界定位，非通用质量声明" if zh else "bounded localization, not general", GREEN),
                ("Risk", "诊断 Release；预测仍 UNKNOWN" if zh else "diagnosis released; forecast UNKNOWN", AMBER),
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
                f'<text x="90" y="850" font-size="16" fill="{MUTED}">{escape("AET v1.19 · 本地 Evidence Plane · 权威永不自动升级" if zh else "AET v1.19 · local Evidence Plane · authority never auto-promotes")}</text>',
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
