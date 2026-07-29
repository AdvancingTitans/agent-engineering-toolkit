"""Validation results and Candidate validators."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    code: str
    message: str

    @property
    def invalid(self) -> bool:
        return not self.valid


from .anti_gaming import detect_gaming
from .grounding import validate_grounding
from .reference import validate_reference
from .scope import validate_scope
from .strength import validate_strength

__all__ = [
    "ValidationResult",
    "detect_gaming",
    "validate_grounding",
    "validate_reference",
    "validate_scope",
    "validate_strength",
]
