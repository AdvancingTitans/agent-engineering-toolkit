"""Target adapters and the fail-closed target registry."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Protocol, runtime_checkable


class TargetResolutionError(ValueError):
    pass


@runtime_checkable
class EvolutionTargetAdapter(Protocol):
    target_type: str
    status: str

    def inspect_target(self, path: Path) -> Any: ...

    def build_candidate(self, baseline: bytes, patterns: list[dict[str, Any]], proposal: dict[str, Any]) -> Any: ...

    def validate_candidate(self, candidate: Any) -> list[str]: ...

    def replay(self, baseline: Any, candidate: Any, suite: Path) -> Any: ...

    def adopt(self, candidate: Any, authorization: Any) -> Any: ...

    def validate_operations(self, operations: tuple[dict[str, Any], ...]) -> None: ...


@dataclass(frozen=True)
class BoundedTargetAdapter:
    target_type: str
    status: str

    def inspect_target(self, path: Path) -> Any:
        from .constitution import CONSTITUTION
        resolved = path.resolve()
        if not resolved.is_file() or not CONSTITUTION.permits_target(str(resolved)):
            raise ValueError(f"{self.target_type} target is missing or forbidden")
        raw = resolved.read_bytes()
        if self.target_type == "skill":
            value: Any = raw.decode("utf-8")
            schema = "skill-markdown"
        else:
            value = json.loads(raw)
            schema = value.get("schema_version") if isinstance(value, dict) else None
        return {"target_type": self.target_type, "path": str(resolved), "sha256": hashlib.sha256(raw).hexdigest(), "schema_version": schema, "value": value}

    def build_candidate(self, baseline: bytes, patterns: list[dict[str, Any]], proposal: dict[str, Any]) -> Any:
        operations = proposal.get("operations")
        if not isinstance(operations, list):
            raise ValueError("proposal must contain operations")
        self.validate_operations(tuple(operations))
        if self.target_type == "skill":
            candidate = proposal.get("candidate_text")
            if not isinstance(candidate, str):
                raise ValueError("Skill proposal requires candidate_text")
            return candidate.encode()
        document = json.loads(baseline)
        for operation in operations:
            _apply_json_pointer(document, operation)
        return (json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode()

    def validate_candidate(self, candidate: Any) -> list[str]:
        target = getattr(getattr(candidate, "target", None), "target_type", None)
        if target != self.target_type:
            return [f"candidate target {target!r} does not match adapter {self.target_type!r}"]
        try:
            self.validate_operations(tuple(candidate.operations))
        except ValueError as error:
            return [str(error)]
        return []

    def replay(self, baseline: Any, candidate: Any, suite: Path) -> Any:
        if self.target_type == "skill":
            from ..learn import _evaluate
            before = baseline.decode() if isinstance(baseline, bytes) else str(baseline)
            after = candidate.decode() if isinstance(candidate, bytes) else str(candidate)
            return {"baseline": _evaluate(before, [suite]), "candidate": _evaluate(after, [suite])}
        if self.target_type == "audit-rule":
            from ..audit_evolution import evaluate_audit_suite
            return {"baseline": evaluate_audit_suite(rulepack=baseline, suite=suite), "candidate": evaluate_audit_suite(rulepack=candidate, suite=suite)}
        from ..policy_targets import evaluate_policy_suite
        return {"baseline": evaluate_policy_suite(policy=baseline, target_type=self.target_type, suite=suite), "candidate": evaluate_policy_suite(policy=candidate, target_type=self.target_type, suite=suite)}

    def adopt(self, candidate: Any, authorization: Any) -> Any:
        if not isinstance(authorization, dict) or authorization.get("yes") is not True:
            raise ValueError("adoption requires explicit human authorization")
        target = Path(authorization["target"])
        expected = authorization.get("baseline_sha256")
        if hashlib.sha256(target.read_bytes()).hexdigest() != expected:
            raise ValueError("production target no longer matches the baseline hash")
        content = authorization.get("content")
        if not isinstance(content, bytes):
            raise ValueError("adoption requires validated candidate bytes")
        temporary = target.with_suffix(target.suffix + ".tmp")
        temporary.write_bytes(content)
        temporary.replace(target)
        return {"status": "PASS", "target_type": self.target_type, "target": str(target)}

    def validate_operations(self, operations: tuple[dict[str, Any], ...]) -> None:
        if not operations:
            raise ValueError("candidate must contain at least one operation")
        prefixes = {
            "skill": ("/editable_blocks/",),
            "audit-rule": ("/rulepack_id", "/revision", "/rules/-"),
            "audit-profile": ("/rules/", "/path_policy/", "/exclusions"),
            "review-policy": ("/changed_path_budget", "/path_classes/", "/proof_requirements/"),
            "trace-validator": ("/requirements/",),
            "triage-policy": ("/weights/", "/critical_paths"),
        }[self.target_type]
        for operation in operations:
            path = operation.get("path") if isinstance(operation, dict) else None
            if not isinstance(path, str) or not any(path == prefix or path.startswith(prefix) for prefix in prefixes):
                raise ValueError(f"operation path is outside the {self.target_type} allowlist")


class TargetRegistry:
    def __init__(self) -> None:
        self._adapters: dict[str, EvolutionTargetAdapter] = {}

    def register(self, adapter: EvolutionTargetAdapter) -> None:
        if adapter.status not in {"supported", "experimental"}:
            raise TargetResolutionError(f"invalid target status: {adapter.status}")
        if not adapter.target_type or adapter.target_type in self._adapters:
            raise TargetResolutionError(f"duplicate or empty target type: {adapter.target_type}")
        self._adapters[adapter.target_type] = adapter

    def get(self, target_type: str) -> EvolutionTargetAdapter:
        try:
            return self._adapters[target_type]
        except KeyError as error:
            raise TargetResolutionError(f"unknown evolution target type: {target_type}") from error

    def list(self) -> tuple[EvolutionTargetAdapter, ...]:
        return tuple(self._adapters[name] for name in sorted(self._adapters))


def default_registry() -> TargetRegistry:
    registry = TargetRegistry()
    for target_type, status in (
        ("skill", "supported"),
        ("audit-rule", "supported"),
        ("audit-profile", "supported"),
        ("review-policy", "supported"),
        ("trace-validator", "supported"),
        ("triage-policy", "supported"),
    ):
        registry.register(BoundedTargetAdapter(target_type, status))
    return registry


def infer_target_type(path: Path) -> str:
    """Only the legacy SKILL.md convention is safe to infer."""
    if path.name == "SKILL.md":
        return "skill"
    raise TargetResolutionError("non-Skill evolution targets require an explicit target type")


def _apply_json_pointer(document: dict[str, Any], operation: dict[str, Any]) -> None:
    path = operation["path"]
    parts = [part.replace("~1", "/").replace("~0", "~") for part in path.split("/")[1:]]
    current: Any = document
    for part in parts[:-1]:
        current = current[part]
    leaf = parts[-1]
    if isinstance(current, list) and leaf == "-":
        current.append(operation.get("value"))
    else:
        current[leaf] = operation.get("value")
