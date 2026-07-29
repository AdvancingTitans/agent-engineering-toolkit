"""Installed-package demonstrations backed by the real AET Quick core."""

from .models import DemoOptions, DemoResult
from .registry import get_demo, list_demos
from .runner import run_demo

__all__ = ["DemoOptions", "DemoResult", "get_demo", "list_demos", "run_demo"]
