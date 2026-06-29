"""Backing implementation for the `latency_p95` signal.metric (clean fixture).

acceptance URN: acc:checkout:E019-METRIC-001-latency-budget
threshold: 200
passes when: value <= threshold (upper-bound)
"""
from __future__ import annotations

from pathlib import Path


def compute(repo_root: Path) -> int:
    """Return the metric's current value (stub: zero offending sites)."""
    return 0


def passes(value, threshold) -> bool:
    """Upper-bound metric: pass when value <= threshold."""
    return value <= threshold
