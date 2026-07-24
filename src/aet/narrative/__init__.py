"""Language routing and human narrative rendering for Quick Skills."""

from .renderer import render_investigated_finding, render_quick_result
from .terminology import select_language

__all__ = ["render_investigated_finding", "render_quick_result", "select_language"]
