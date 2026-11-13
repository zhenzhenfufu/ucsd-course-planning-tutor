"""Adapters for each department's tentative course plan. Each takes page text, not a session."""

from . import cogs, cse, dsc, ece, math, phys
from ._common import ShapeError

ADAPTERS = {m.DEPARTMENT: m for m in (dsc, cse, math, cogs, phys, ece)}

__all__ = ["ADAPTERS", "ShapeError"]
