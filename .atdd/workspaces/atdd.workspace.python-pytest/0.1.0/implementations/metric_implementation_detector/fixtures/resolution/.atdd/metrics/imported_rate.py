"""`compute` as an IMPORTED name (bound by import, not `def`).

Resolves under import + callable() resolution; a `^def compute` regex would
falsely flag it because there is no `def compute(` line.
"""
from __future__ import annotations

from statistics import fmean as compute  # callable bound via import, no `def`
