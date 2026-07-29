"""Render a bounded Improvement summary for a pull request."""

from __future__ import annotations

from ..models.constraint import ImprovementConstraint
from ..models.issue import ImprovementIssue


def render_github_comment(
    issues: list[ImprovementIssue],
    constraints: list[ImprovementConstraint],
) -> str:
    """Render deterministic Markdown without merge authority."""
    by_issue = {item.issue_id: item for item in constraints}
    lines = [
        "## Improvement Summary",
        "",
        "> Candidate recommendations are non-authoritative and do not block merge.",
        "",
    ]
    for issue in issues:
        lines.append(
            f"- **{issue.id} · {issue.priority}** {issue.title} — "
            f"{by_issue[issue.id].objective}"
        )
    if not issues:
        lines.append("- No actionable improvements were derived.")
    return "\n".join(lines) + "\n"
