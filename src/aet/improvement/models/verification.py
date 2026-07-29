"""Verification Contract model."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class VerificationContract:
    id: str
    commands: list[str]
    expected_results: list[str]
    proof_required: bool
    relevant_paths: list[str]
