"""``atdd coach transition <N> <TO>`` — auto-discovered drop-in (#1304).

This is the reference implementation of the coach-verb registration convention
documented in ``coach_verbs/__init__.py``. It declares the verb token and points
at the logic module — nothing more. C2–C4 (#1305/#1307/#1308) add their verb by
copying this two-line shape into a new sibling file; no shared wiring is touched.
"""
from __future__ import annotations

from atdd.coach.commands.issue_transition import run  # noqa: F401  (verb entry point)

VERB = "transition"
