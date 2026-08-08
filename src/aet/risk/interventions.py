"""Fixed, proposal-only intervention routing for observed factor combinations."""

from __future__ import annotations

import hashlib
from collections import defaultdict
from typing import Iterable

from .models import Factor, FactorFinding, ProposedIntervention, RiskPathway, SourceRef, Status

_ACTIONS = {
    frozenset({Factor.GOAL_DIVERGENCE}): (
        "pause the next step",
        "re-anchor explicit Intent v2",
        "require explicit scope confirmation without adding permissions",
    ),
    frozenset({Factor.HARM_REALIZATION_CAPABILITY}): (
        "apply least privilege and sandboxing",
        "require dry-run and step-up approval for protected actions",
    ),
    frozenset({Factor.OVERSIGHT_RESISTANCE}): (
        "enable an out-of-band monitor",
        "retain raw results and produce tamper-evident Proof",
    ),
    frozenset({Factor.GOAL_DIVERGENCE, Factor.HARM_REALIZATION_CAPABILITY}): (
        "pause write, execute, and network access",
        "snapshot state and request human scope review",
    ),
    frozenset({Factor.GOAL_DIVERGENCE, Factor.OVERSIGHT_RESISTANCE}): (
        "stop the current run",
        "preserve complete logs and request independent review",
    ),
    frozenset({Factor.HARM_REALIZATION_CAPABILITY, Factor.OVERSIGHT_RESISTANCE}): (
        "revoke high-impact tools",
        "isolate the environment and hand off to a human",
    ),
    frozenset(Factor): (
        "recommend containment or termination to the Agent Host",
        "recommend revoking temporary credentials",
        "snapshot state and escalate to the responsible security owner",
    ),
}


def propose_interventions(
    findings: Iterable[FactorFinding],
    pathways: Iterable[RiskPathway] = (),
) -> tuple[ProposedIntervention, ...]:
    grouped: dict[str, list[FactorFinding]] = defaultdict(list)
    for finding in findings:
        if finding.status is Status.FAIL:
            grouped[finding.context_key].append(finding)
    proposals: list[ProposedIntervention] = []
    for context_key, failed in sorted(grouped.items()):
        factors = frozenset(item.factor for item in failed)
        actions = _ACTIONS.get(factors)
        if not actions:
            continue
        ordered_factors = tuple(sorted(factors, key=lambda item: item.value))
        refs = _unique_refs(ref for item in failed for ref in item.evidence_refs)
        identity = context_key + "|" + "|".join(item.value for item in ordered_factors)
        proposals.append(
            ProposedIntervention(
                intervention_id="risk-intervention-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16],
                context_key=context_key,
                factor_combination=ordered_factors,
                authority="PROPOSED",
                actions=actions,
                rationale_refs=refs,
            )
        )
    return tuple(proposals)


def _unique_refs(values) -> tuple[SourceRef, ...]:
    result: list[SourceRef] = []
    seen: set[str] = set()
    for value in values:
        if value.ref not in seen:
            seen.add(value.ref)
            result.append(value)
    return tuple(result)


__all__ = ["propose_interventions"]
