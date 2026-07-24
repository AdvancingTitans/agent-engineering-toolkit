"""Host-neutral contracts for bounded, evidence-grounded investigations."""

from .grounding import GroundingError, validate_investigated_finding
from .ledger import InvestigationLedger
from .models import (
    FindingOrigin,
    ScopeDisposition,
    SupportState,
)
from .stop_policy import CommandBudget, StopDecision, evaluate_stop

__all__ = [
    "CommandBudget",
    "FindingOrigin",
    "GroundingError",
    "InvestigationLedger",
    "ScopeDisposition",
    "StopDecision",
    "SupportState",
    "evaluate_stop",
    "validate_investigated_finding",
]
