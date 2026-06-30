"""`compute` as a LAMBDA (no `def compute`, no `passes`).

Resolves under import + callable() resolution; a `^def compute` regex would
falsely flag it.
"""
from __future__ import annotations

compute = lambda repo_root: 0  # noqa: E731 — deliberately non-`def` callable
