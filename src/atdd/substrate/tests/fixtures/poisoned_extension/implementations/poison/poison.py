"""POISONED implementation module.

Executing this module (import OR call) is a CONTRACT VIOLATION during admission:
it records a sentinel file (path from ATDD_C001_SENTINEL) and raises. Admission
must never import or run it, so in a correct run the sentinel is never written
and this RuntimeError never surfaces.
"""
import os
import pathlib

_sentinel = os.environ.get("ATDD_C001_SENTINEL")
if _sentinel:
    pathlib.Path(_sentinel).write_text("EXECUTED-AT-IMPORT", encoding="utf-8")

raise RuntimeError("POISONED: implementation code executed during admission")


def run(*args, **kwargs):  # pragma: no cover - never reached (import raises first)
    raise RuntimeError("POISONED: implementation called during admission")
