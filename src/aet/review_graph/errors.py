"""Review Graph errors with stable machine-readable codes."""

from __future__ import annotations


class ReviewGraphError(ValueError):
    """A Review Graph input or projection failed closed."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")
