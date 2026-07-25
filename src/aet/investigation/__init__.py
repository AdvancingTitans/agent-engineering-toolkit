"""Host-neutral contracts for bounded, evidence-grounded investigations."""

from .grounding import GroundingError, validate_investigated_finding
from .ledger import InvestigationLedger
from .models import (
    FindingOrigin,
    ScopeDisposition,
    SupportState,
)
from .portable import (
    PortableInvestigationError,
    investigate_run,
    validate_investigation_result,
    write_investigation_result,
)
from .stop_policy import CommandBudget, StopDecision, evaluate_stop

__all__ = [
    "CommandBudget",
    "FindingOrigin",
    "GroundingError",
    "InvestigationLedger",
    "PortableInvestigationError",
    "ScopeDisposition",
    "StopDecision",
    "SupportState",
    "evaluate_stop",
    "investigate_run",
    "validate_investigation_result",
    "validate_investigated_finding",
    "write_investigation_result",
]
