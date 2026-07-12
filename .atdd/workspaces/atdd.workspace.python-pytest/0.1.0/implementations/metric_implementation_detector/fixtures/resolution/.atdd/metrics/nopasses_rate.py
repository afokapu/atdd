"""A valid `def compute` module with NO `passes`.

Resolves under the legacy contract (only a callable `compute` is required); the
regressed regex falsely required a `^def passes` symbol and flagged this.
"""
from __future__ import annotations

from pathlib import Path


def compute(repo_root: Path) -> int:
    return 0
