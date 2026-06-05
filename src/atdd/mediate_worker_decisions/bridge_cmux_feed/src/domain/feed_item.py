"""Domain value objects for the cmux Feed bridge (pure, no I/O).

``FeedItem`` mirrors one entry from ``cmux rpc feed.list`` — a pending agent
decision (question / permission / exitPlan). ``FeedReplyPlan`` is the resolved
intent to reply: which ``feed.*.reply`` verb to call and with which params. Both
are frozen and built only from plain data, so the mappers stay unit-testable
without any cmux dependency.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional, Tuple

# feed item kinds, exactly as cmux emits them. NB cmux uses ``permissionRequest``
# (NOT ``permission``) for tool/shell permission decisions — verified live against
# ``cmux rpc feed.list`` (#981). The mismatch silently dropped every permission
# item in CmuxFeedSource, so permission mediation never surfaced.
QUESTION = "question"
PERMISSION = "permissionRequest"
EXIT_PLAN = "exitPlan"


@dataclass(frozen=True)
class FeedItem:
    """A single pending decision read from the cmux Feed."""

    id: str
    request_id: str
    kind: str  # QUESTION | PERMISSION | EXIT_PLAN
    question_prompt: Optional[str] = None
    # each option is a plain mapping: {"id", "label", "description"}
    question_options: Tuple[Mapping[str, str], ...] = field(default_factory=tuple)
    tool_name: Optional[str] = None
    tool_input: Optional[str] = None
    # The FULL multi-question payload as cmux emits it: each entry is a plain
    # mapping {"id", "header", "prompt", "multi_select", "options":[...], and an
    # optional "kind"}. ``question_prompt``/``question_options`` above are a
    # convenience mirror of the FIRST question only; ``questions`` carries them
    # all so the mapper can preserve the whole decision document (WMBT L003).
    questions: Tuple[Mapping[str, Any], ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class FeedReplyPlan:
    """The resolved reply intent for one feed item.

    ``verb`` is the cmux RPC verb (``feed.question.reply`` /
    ``feed.permission.reply`` / ``feed.exit_plan.reply``); ``params`` is the JSON
    payload that verb expects (always carrying ``request_id``).
    """

    verb: str
    params: Mapping[str, Any]
