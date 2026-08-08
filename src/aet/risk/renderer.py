"""Canonical and human-readable behavioural-risk report rendering."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Mapping

from .errors import RiskInputError
from .models import RiskDiagnosis, to_primitive
from .schemas import SchemaKind, validate_version


def render_json(diagnosis: RiskDiagnosis) -> str:
    value = to_primitive(diagnosis)
    validate_version(SchemaKind.RISK_DIAGNOSIS, value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"


def render_markdown(diagnosis: RiskDiagnosis) -> str:
    lines = [
        "# AET Behavioural Risk Diagnosis",
        "",
        f"- Schema: `{diagnosis.schema_version}`",
        f"- Policy: `{diagnosis.policy_id}` (`{diagnosis.policy_sha256}`)",
        f"- Created: `{diagnosis.created_at}`",
        "- Authority: evidence-grounded diagnosis; interventions are proposals only",
        "",
        "## Risk vector",
        "",
        "| Factor | Status | Strength | Evidence | Coverage |",
        "|---|---|---|---|---|",
    ]
    for finding in diagnosis.findings:
        evidence = ", ".join(f"`{item.ref}`" for item in finding.evidence_refs) or "—"
        coverage = "complete" if finding.coverage.complete else "gaps: " + ", ".join(finding.coverage.gaps)
        lines.append(
            f"| `{finding.factor.value}` | **{finding.status.value}** | {finding.strength.value} | {evidence} | {coverage} |"
        )
    lines.extend(["", "## Limitations", ""])
    for finding in diagnosis.findings:
        lines.append(f"### `{finding.factor.value}`")
        lines.append("")
        lines.append("Does not prove: " + "; ".join(finding.does_not_prove) + ".")
        lines.append("")
        for limitation in finding.limitations:
            lines.append(f"- {limitation}")
        lines.append("")
    if diagnosis.pathways:
        lines.extend(["## Pathways", ""])
        for pathway in diagnosis.pathways:
            lines.append(f"- `{pathway.pathway_id}`: **{pathway.status.value}**")
        lines.append("")
    if diagnosis.interventions:
        lines.extend(["## Proposed interventions", ""])
        for intervention in diagnosis.interventions:
            lines.append(f"- `{intervention.intervention_id}` (`PROPOSED`): " + "; ".join(intervention.actions))
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def write_outputs(
    diagnosis: RiskDiagnosis,
    json_out: str | Path,
    md_out: str | Path | None = None,
) -> tuple[Path, Path | None]:
    targets = [Path(json_out)] + ([Path(md_out)] if md_out is not None else [])
    if len({path.resolve(strict=False) for path in targets}) != len(targets):
        raise RiskInputError("JSON and Markdown outputs must be different paths")
    for path in targets:
        if path.is_symlink():
            raise RiskInputError("risk output cannot be a symbolic link")
        if path.exists():
            raise RiskInputError(f"risk output already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
    content = [render_json(diagnosis)] + ([render_markdown(diagnosis)] if md_out is not None else [])
    temporary: list[Path] = []
    published: list[Path] = []
    try:
        for target, text in zip(targets, content, strict=True):
            handle, name = tempfile.mkstemp(prefix=f".{target.name}.", dir=target.parent)
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
            temporary.append(Path(name))
        for source, target in zip(temporary, targets, strict=True):
            os.link(source, target, follow_symlinks=False)
            published.append(target)
            source.unlink()
    except OSError as error:
        for path in reversed(published):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        raise RiskInputError(f"cannot write risk output: {error}") from error
    finally:
        for path in temporary:
            try:
                path.unlink()
            except FileNotFoundError:
                pass
    return targets[0], targets[1] if len(targets) == 2 else None


__all__ = ["render_json", "render_markdown", "write_outputs"]
