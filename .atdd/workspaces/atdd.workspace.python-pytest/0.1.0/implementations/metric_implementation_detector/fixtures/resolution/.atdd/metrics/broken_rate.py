"""A metric module that EXISTS but FAILS TO IMPORT.

A `^def compute` regex sees the text and (wrongly) considers it present; an
import sees the error. The legacy oracle imports, so it flags this as a missing
implementation. This module must be the ONLY violation the resolution fixture
produces.
"""
from __future__ import annotations

import _atdd_nonexistent_dependency_xyz  # noqa: F401 — deliberate import failure


def compute(repo_root):  # never reached: the import above raises first
    return 0
