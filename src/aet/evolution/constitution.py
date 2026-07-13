"""Canonical safety boundary shared by every evolution target."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json


@dataclass(frozen=True)
class EvolutionConstitution:
    immutable_semantics: frozenset[str]
    forbidden_targets: frozenset[str]

    def permits_target(self, target: str) -> bool:
        """Fail closed for exact symbols, exact paths, and held-out trees."""
        normalized = "/" + target.replace("\\", "/").strip("/")
        for forbidden in self.forbidden_targets:
            path = forbidden.split("::", 1)[0].strip("/")
            if forbidden.endswith("/**"):
                prefix = path[:-3].rstrip("/")
                if normalized.endswith("/" + prefix) or "/" + prefix + "/" in normalized:
                    return False
            elif normalized.endswith("/" + path):
                return False
        return True


CONSTITUTION = EvolutionConstitution(
    immutable_semantics=frozenset(
        {
            "unknown_is_not_pass",
            "natural_language_is_not_execution_proof",
            "candidate_cannot_modify_evaluator",
            "held_out_must_be_separate",
            "adoption_requires_human_authorization",
            "production_target_must_match_baseline_hash",
            "candidate_may_not_reduce_existing_hard_failures",
            "shadow_candidate_may_not_affect_official_exit_code",
        }
    ),
    forbidden_targets=frozenset(
        {
            "src/aet/models.py::Status",
            "src/aet/learn_statistics.py",
            "src/aet/evolution/constitution.py",
            "src/aet/evolution/evaluators/**",
            "src/aet/evolution/gates.py",
            "schemas/evolution-constitution-v1.json",
            "held_out/**",
        }
    ),
)


def constitution_sha256() -> str:
    payload = json.dumps({"immutable_semantics": sorted(CONSTITUTION.immutable_semantics), "forbidden_targets": sorted(CONSTITUTION.forbidden_targets)}, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()
