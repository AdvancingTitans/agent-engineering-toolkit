"""Lightweight Quick surfaces built on the stable deterministic AET core."""

from .check import quick_check
from .fresh import quick_fresh
from .proof import quick_proof
from .scope import quick_scope

__all__ = ["quick_check", "quick_fresh", "quick_proof", "quick_scope"]
