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
    title = "AET 项目架构全景" if zh else "AET Project Architecture Panorama"
    subtitle = (
        "四个日常入口，共享一套证据协议；LLM 调查与确定性校验分权；Lab 始终显式启用"
        if zh
        else "Four daily entry points, one evidence protocol; LLM investigation and deterministic validation have separate authority"
    )
    section_titles = (
        ("用户入口", "Quick 运行时", "共享证据与契约", "显式启用的 AET Lab")
        if zh
        else ("User-facing entry points", "Quick runtime", "Shared evidence and contracts", "Explicit opt-in AET Lab")
    )
    cards = {
        "skills": ("开发者请求", "任务目标 · 限制 · 显式授权", "") if zh else ("Developer request", "goal · constraints · explicit authority", ""),
        "cli": ("四个 Quick Skill", "Check · Scope · Proof · Fresh", "skills/aet-*") if zh else ("Four Quick Skills", "Check · Scope · Proof · Fresh", "skills/aet-*"),
        "host": ("Agent Host", "LLM 规划授权工具调用", "skills/*/SKILL.md") if zh else ("Agent Host", "LLM plans authorized tool calls", "skills/*/SKILL.md"),
        "human": ("人工决定", "修复 · 拆分 · 继续验证 · 显式进入 Lab", "") if zh else ("Human decision", "fix · split · verify · explicitly enter Lab", ""),
        "handlers": ("CLI 路由与权限", "参数 · 语言 · 命令边界", "src/aet/cli.py") if zh else ("CLI routing & authority", "arguments · language · command boundary", "src/aet/cli.py"),
        "investigate": ("Quick 处理器与预检", "最小事实集 · 有界结果", "src/aet/quick/*") if zh else ("Quick handlers & preflight", "minimal facts · bounded result", "src/aet/quick/*"),
        "ledger": ("受控调查与记录", "任务意图 · 反方解释 · 工具结果", "investigation/* · ledger.py") if zh else ("Investigation & record", "intent · counter-case · tool results", "investigation/* · ledger.py"),
        "validator": ("依据校验与叙事", "引用 · 权限 · 强度 · 中文表达", "grounding.py · narrative/*") if zh else ("Grounding & narrative", "references · authority · strength · language", "grounding.py · narrative/*"),
        "evidence": ("命令与权限契约", "预算 · 语言 · 停止规则", "schemas/command-budget* · cli.py") if zh else ("Command & authority contracts", "budgets · language · stop rules", "schemas/command-budget* · cli.py"),
        "binding": ("证据、Proof 与时效", "PASS · FAIL · UNKNOWN · 文件绑定", "evidence.py · quick/proof.py · fresh.py") if zh else ("Evidence, proof & freshness", "PASS · FAIL · UNKNOWN · file binding", "evidence.py · quick/proof.py · fresh.py"),
        "contracts": ("调查契约与记录 Schema", "引用 · 冲突 · 假设 · 预算", "schemas/investigation-*") if zh else ("Investigation contracts & schemas", "references · conflicts · hypotheses · budget", "schemas/investigation-*"),
        "quality": ("表达、停止策略与测试", "中英叙事 · 拒绝路径 · 对照评测", "narrative/* · tests/* · eval/*") if zh else ("Narrative, stop policy & tests", "bilingual output · rejection paths · evaluation", "narrative/* · tests/* · eval/*"),
        "showcase": ("真实仓库案例库", "SWE-agent · Google ADK · OpenHands", "repository-audit-showcase/*") if zh else ("Real-repository showcase", "SWE-agent · Google ADK · OpenHands", "repository-audit-showcase/*"),
        "memory": ("项目上下文", "Context · Decision · Evolve", "context.py · decision.py · evolve.py") if zh else ("Project provenance", "Context · Decision · Evolve", "context.py · decision.py · evolve.py"),
        "learn": ("质量与演化实验", "Quality · Learn · Replay", "quality.py · learn*.py") if zh else ("Quality & evolution experiments", "Quality · Learn · Replay", "quality.py · learn*.py"),
        "gate": ("受控采纳", "Gate · Shadow · Stage · Adopt", "gate_plan.py · evolution/*") if zh else ("Governed adoption", "Gate · Shadow · Stage · Adopt", "gate_plan.py · evolution/*"),
    }
    lines = _svg_start(1600, 1000, title)
    lines.extend(
        [
            f'<text x="60" y="60" font-size="34" font-weight="800" fill="{TEXT}">{escape(title)}</text>',
            f'<text x="60" y="88" font-size="16" fill="{MUTED}">{escape(subtitle)}</text>',
            f'<text x="1540" y="62" text-anchor="end" class="mono" font-size="13" fill="{GREEN}">AET QUICK / LAB · v1.13+</text>',
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
    _arrow(lines, "M1320 355V261", AMBER, "arrowAmber")
    _arrow(lines, "M230 585V495", GREEN, "arrowGreen", True)
    _arrow(lines, "M590 585V495", BLUE, "arrowBlue", True)
    _arrow(lines, "M950 585V495", PURPLE, "arrowPurple", True)
    _arrow(lines, "M1320 585V495", AMBER, "arrowAmber", True)
    lines.extend(
        [
            f'<rect x="1190" y="776" width="260" height="34" rx="17" fill="{AMBER}" fill-opacity=".13" stroke="{AMBER}" stroke-dasharray="6 6"/>',
            f'<text x="1320" y="798" text-anchor="middle" class="mono" font-size="12" font-weight="800" fill="{AMBER}">{escape("显式命令 + 人工授权" if zh else "EXPLICIT COMMAND + HUMAN AUTHORITY")}</text>',
        ]
    )
    _arrow(lines, "M1490 213H1530V793H1450", AMBER, "arrowAmber", True)
    lines.extend(
        [
            f'<text x="60" y="962" font-size="14" fill="{MUTED}">{escape("实线：Quick 主流程 · 虚线：协议支撑 / 显式进入 Lab" if zh else "Solid: Quick path · dashed: protocol support / explicit Lab entry")}</text>',
            f'<text x="1540" y="962" text-anchor="end" font-size="14" font-weight="700" fill="{TEXT}">{escape("默认本地、只读；只有 /aet-proof 执行显式 argv" if zh else "Local and read-only by default; only /aet-proof executes explicit argv")}</text>',
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
            "Agent 说“修好了”，你真正想确认什么？" if zh else "The Agent says “fixed.” What do you really need to know?",
            "DEVELOPER REALITY" if not zh else "开发者的真实困惑",
            [
                ("改动真的只服务于当前任务吗？" if zh else "Are all changes necessary for this task?", BLUE),
                ("测试真的在当前代码上跑过吗？" if zh else "Did verification actually run on this code?", PURPLE),
                ("测试后代码又变了，旧结果还能用吗？" if zh else "After more edits, does the old result still apply?", AMBER),
            ],
        ),
        (
            "四个命令，各自只解决一个问题" if zh else "Four commands. One question each.",
            "AET QUICK",
            [
                ("/aet-check  检查 Agent 工程规则" if zh else "/aet-check  inspect Agent engineering rules", BLUE),
                ("/aet-scope  判断改动是否为任务所需" if zh else "/aet-scope  investigate whether changes fit the task", PURPLE),
                ("/aet-proof  真正执行并记录一次验证" if zh else "/aet-proof  execute and bind one real verification", GREEN),
                ("/aet-fresh  检查旧验证现在是否仍适用" if zh else "/aet-fresh  check whether old proof still applies", AMBER),
            ],
        ),
        (
            "路径不一致，只是线索，不是定罪" if zh else "A path mismatch is a clue, not a verdict.",
            "范围调查" if zh else "SCOPE INVESTIGATION",
            [
                ("auth/session.py", "IN_SCOPE", BLUE),
                ("cache/session_cache.py", "JUSTIFIED_EXPANSION", GREEN),
                ("payment/order.py", "POSSIBLE_SCOPE_EXPANSION", AMBER),
            ],
        ),
        (
            "把“测试通过”绑定到当时的代码" if zh else "Bind “tests passed” to the code that was tested.",
            "验证记录 + 结果时效" if zh else "PROOF + FRESHNESS",
            [
                ("命令参数 + 退出码" if zh else "argv + exit code", "pytest tests/auth → 18 passed", BLUE),
                ("工作区绑定" if zh else "Workspace binding", "Git HEAD + 相关文件哈希" if zh else "Git HEAD + relevant file hashes", GREEN),
                ("结果时效" if zh else "Freshness", "文件已变化 → RELEVANT_FILES_CHANGED" if zh else "file changed → RELEVANT_FILES_CHANGED", AMBER),
            ],
        ),
        (
            "工具给事实，LLM 负责追问，校验器守住底线" if zh else "Tools provide facts. The LLM investigates. The validator guards the boundary.",
            "有边界的调查" if zh else "BOUNDED INVESTIGATION",
            [
                ("工具事实" if zh else "Tool facts", "Git · 文件 · 测试 · 哈希" if zh else "Git · files · tests · hashes", BLUE),
                ("LLM 调查" if zh else "LLM investigation", "主假设 · 反方解释" if zh else "hypothesis · counter-case", PURPLE),
                ("依据校验" if zh else "Grounding validation", "引用 · 权限 · 预算" if zh else "references · authority · budget", GREEN),
                ("人工决定" if zh else "Human decision", "最小下一步" if zh else "smallest next action", AMBER),
            ],
        ),
        (
            "更有用的审查，也把代价说清楚" if zh else "More useful review, with the cost made explicit.",
            "有数据的取舍" if zh else "MEASURED TRADE-OFF",
            [
                ("90% 有效召回" if zh else "90% effective recall", "8 个合成 Scope 场景" if zh else "8 synthetic Scope cases", GREEN),
                ("25% 错误发现占比" if zh else "25% false discovery proportion", "不是综合可信度评分" if zh else "not a trust score", BLUE),
                ("0.75 平均工具调用" if zh else "0.75 mean tool calls", "带依据约束的调查组" if zh else "grounding-aware group", PURPLE),
                ("不自动修复、合并、发布" if zh else "No automatic fix, merge, or release", "最终权限仍由人掌握" if zh else "human authority stays explicit", AMBER),
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
                f'<text x="90" y="850" font-size="16" fill="{MUTED}">{escape("AET Quick · 日常 AI Coding 的证据调查层" if zh else "AET Quick · the evidence investigation layer for daily AI coding")}</text>',
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
