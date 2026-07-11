"""``atdd coach issues [open|<N>]`` — auto-discovered drop-in (#1307, C3).

Copies the C1 (#1304) coach-verb registration shape (see ``transition.py`` and
the convention in ``coach_verbs/__init__.py``): declare the verb token and point
at the logic module — nothing more. The read logic is delegation-only
(``issue_read.run`` calls the existing ``IssueManager.open_issues`` /
``IssueLifecycle.enter``), and this file touches no shared wiring, so it never
merge-conflicts with the sibling verbs (#1305/#1308).
"""
from __future__ import annotations

from atdd.coach.commands.issue_read import run  # noqa: F401  (verb entry point)

VERB = "issues"
