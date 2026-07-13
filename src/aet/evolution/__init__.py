"""Public primitives for evidence-gated, multi-target evolution."""

from .candidate import CandidateError, CandidateTarget, EvolutionCandidate, load_candidate
from .constitution import CONSTITUTION, EvolutionConstitution, constitution_sha256
from .targets import (
    EvolutionTargetAdapter,
    TargetRegistry,
    TargetResolutionError,
    default_registry,
    infer_target_type,
)

__all__ = [
    "CONSTITUTION",
    "CandidateError",
    "CandidateTarget",
    "EvolutionCandidate",
    "EvolutionConstitution",
    "EvolutionTargetAdapter",
    "TargetRegistry",
    "TargetResolutionError",
    "default_registry",
    "infer_target_type",
    "load_candidate",
    "constitution_sha256",
]
