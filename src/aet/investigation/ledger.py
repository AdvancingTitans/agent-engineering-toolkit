"""Investigation Ledger validation and immutable result references."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class LedgerError(ValueError):
    """Raised when an investigation ledger is incomplete or inconsistent."""


@dataclass(frozen=True)
class InvestigationLedger:
    data: dict[str, Any]

    @classmethod
    def load(cls, path: Path) -> "InvestigationLedger":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise LedgerError(f"cannot read investigation ledger: {error}") from error
        ledger = cls(data)
        ledger.validate()
        return ledger

    def validate(self) -> None:
        schema = self.data.get("schema_version", self.data.get("schema"))
        if schema != "aet-investigation-ledger/v1":
            raise LedgerError("ledger schema must be aet-investigation-ledger/v1")
        if not isinstance(self.data.get("investigation_id"), str) or not self.data["investigation_id"]:
            raise LedgerError("ledger investigation_id must be a non-empty string")
        if self.data.get("command") not in {"aet-check", "aet-scope", "aet-proof", "aet-fresh"}:
            raise LedgerError("ledger command is invalid")
        hypotheses = self.data.get("hypotheses")
        if not isinstance(hypotheses, list):
            raise LedgerError("ledger hypotheses must be a list")
        hypothesis_ids: set[str] = set()
        for hypothesis in hypotheses:
            if not isinstance(hypothesis, dict):
                raise LedgerError("every hypothesis must be an object")
            identifier = hypothesis.get("id")
            if not isinstance(identifier, str) or not identifier or identifier in hypothesis_ids:
                raise LedgerError("hypothesis ids must be unique non-empty strings")
            hypothesis_ids.add(identifier)
        completed = self.data.get("completed_investigations")
        if (
            not isinstance(completed, list)
            or not all(isinstance(item, str) and item for item in completed)
            or len(set(completed)) != len(completed)
        ):
            raise LedgerError("ledger completed_investigations must be unique non-empty strings")
        conflicts = self.data.get("material_conflicting_evidence_refs")
        if (
            not isinstance(conflicts, list)
            or not all(isinstance(item, str) and item for item in conflicts)
            or len(set(conflicts)) != len(conflicts)
        ):
            raise LedgerError(
                "ledger material_conflicting_evidence_refs must be unique non-empty strings"
            )
        self._validate_budget()
        steps = self.data.get("steps")
        if not isinstance(steps, list):
            raise LedgerError("ledger steps must be a list")
        identifiers: set[str] = set()
        result_refs: set[str] = set()
        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                raise LedgerError(f"ledger step {index} must be an object")
            required = (
                "step_id",
                "question",
                "tool",
                "input",
                "result",
                "result_ref",
                "result_sha256",
                "observation",
                "hypothesis_effect",
                "decision_value",
                "cost",
            )
            missing = [field for field in required if field not in step]
            if missing:
                raise LedgerError(f"ledger step {index} is missing: {', '.join(missing)}")
            identifier = step["step_id"]
            result_ref = step["result_ref"]
            if not isinstance(identifier, str) or not identifier or identifier in identifiers:
                raise LedgerError("ledger step_id values must be unique non-empty strings")
            if not isinstance(result_ref, str) or not result_ref.startswith("evidence://"):
                raise LedgerError(f"ledger step {identifier} has an invalid result_ref")
            digest = step["result_sha256"]
            if (
                not isinstance(digest, str)
                or len(digest) != 64
                or any(character not in "0123456789abcdef" for character in digest)
            ):
                raise LedgerError(f"ledger step {identifier} needs a SHA-256 result binding")
            actual_digest = hashlib.sha256(
                json.dumps(
                    step["result"],
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            if digest != actual_digest:
                raise LedgerError(f"ledger step {identifier} result binding does not match its result")
            effect = step.get("hypothesis_effect")
            if not isinstance(effect, dict):
                raise LedgerError(f"ledger step {identifier} has an invalid hypothesis_effect")
            affected = list(effect.get("supports", [])) + list(effect.get("weakens", []))
            unknown_hypotheses = [item for item in affected if item not in hypothesis_ids]
            if unknown_hypotheses:
                raise LedgerError(
                    f"ledger step {identifier} references unknown hypotheses: "
                    + ", ".join(unknown_hypotheses)
                )
            identifiers.add(identifier)
            result_refs.add(result_ref)
        if len(result_refs) != len(steps):
            raise LedgerError("ledger result_ref values must be unique")
        unknown_conflicts = [ref for ref in conflicts if ref not in result_refs]
        if unknown_conflicts:
            raise LedgerError(
                "ledger material conflicts reference unknown evidence: "
                + ", ".join(unknown_conflicts)
            )
        stop = self.data.get("stop")
        if not isinstance(stop, dict) or not isinstance(stop.get("bounded_result"), bool):
            raise LedgerError("ledger stop decision is missing or invalid")

    def _validate_budget(self) -> None:
        budget = self.data.get("budget")
        usage = self.data.get("usage")
        if not isinstance(budget, dict) or not isinstance(usage, dict):
            raise LedgerError("ledger budget and usage are required")
        for field in (
            "wall_time_seconds",
            "llm_calls",
            "tool_calls",
            "remote_calls",
            "expensive_calls",
            "findings",
        ):
            limit = budget.get(field)
            consumed = usage.get(field)
            if (
                not isinstance(limit, (int, float))
                or isinstance(limit, bool)
                or limit < 0
                or not isinstance(consumed, (int, float))
                or isinstance(consumed, bool)
                or consumed < 0
            ):
                raise LedgerError(f"ledger budget field {field} must be non-negative")
            if consumed > limit:
                raise LedgerError(f"ledger budget exceeded: {field}")

    @property
    def result_refs(self) -> set[str]:
        return {step["result_ref"] for step in self.data.get("steps", [])}

    def step_for(self, result_ref: str) -> dict[str, Any]:
        for step in self.data.get("steps", []):
            if step.get("result_ref") == result_ref:
                return step
        raise LedgerError(f"unknown result_ref: {result_ref}")

    def digest(self) -> str:
        raw = json.dumps(self.data, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        return hashlib.sha256(raw).hexdigest()
