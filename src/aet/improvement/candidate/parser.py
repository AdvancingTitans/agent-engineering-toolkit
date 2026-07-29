"""Parse a validated Candidate response."""

from __future__ import annotations

import json
from typing import Any, Mapping

from ..models.candidate import CodeTarget, ImprovementCandidate
from .schema import CandidateSchema


def parse_candidate(raw: str | Mapping[str, Any]) -> ImprovementCandidate:
    """Parse strict JSON or a mapping into the planned Candidate model."""
    value = json.loads(raw) if isinstance(raw, str) else dict(raw)
    CandidateSchema.validate(value)
    return ImprovementCandidate(
        id=value["id"],
        constraint_id=value["constraint_id"],
        strategy=value["strategy"],
        targets=[
            CodeTarget(path=target["path"], symbol=target["symbol"])
            for target in value["targets"]
        ],
        assumptions=list(value["assumptions"]),
        risks=list(value["risks"]),
        verification_plan=list(value["verification_plan"]),
    )
