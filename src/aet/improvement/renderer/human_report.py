"""Human-readable deterministic Improvement report."""

from __future__ import annotations

from collections.abc import Iterable

from ..models.constraint import ImprovementConstraint
from ..models.issue import ImprovementIssue


def render_human_report(
    issue: ImprovementIssue | Iterable[ImprovementIssue],
    constraint: ImprovementConstraint | Iterable[ImprovementConstraint],
) -> str:
    """Render the fixed human report structure from authoritative references."""
    issues = [issue] if isinstance(issue, ImprovementIssue) else list(issue)
    constraints = (
        [constraint]
        if isinstance(constraint, ImprovementConstraint)
        else list(constraint)
    )
    by_issue = {item.issue_id: item for item in constraints}
    lines = ["# Human Improvement Report", ""]
    if not issues:
        return "# Human Improvement Report\n\nNo actionable improvements were derived from the Bundle.\n"
    for item in issues:
        bounded = by_issue[item.id]
        unknowns = list(item.impact.get("limitations", []))
        if item.impact.get("root_cause_status") == "unknown":
            unknowns.append("Root cause is UNKNOWN; investigation is required.")
        lines.extend(
            [
                f"## {item.id} — {item.title}",
                "",
                "### 一句话结论",
                item.impact["statement"],
                "",
                "### 为什么发现",
                f"Finding: {', '.join(item.finding_refs)}; category: `{item.category}`; confidence: `{item.confidence}`.",
                "",
                "### 证据",
                ", ".join(item.evidence_refs) if item.evidence_refs else "INVALID_IMPROVEMENT_INPUT: no Evidence reference.",
                "",
                "### 影响",
                f"Priority: `{item.priority}`. The recorded behavior cannot be treated as safely improved yet.",
                "",
                "### 建议目标",
                bounded.objective,
                "",
                "### 禁止修改",
                "; ".join([*bounded.protected_paths, *bounded.forbidden_behavior]),
                "",
                "### 验证方式",
                "; ".join(bounded.verification_requirements),
                "",
                "### 未知项",
                "; ".join(unknowns) if unknowns else "None recorded.",
                "",
            ]
        )
    return "\n".join(lines)
