"""Feature composition root for bridge-cmux-feed (SPEC-CODER-COMP-0004)."""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

# application
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.application.feed_runner import (
    FeedOutcome,  # noqa: F401
    FeedRunnerUseCase,
)
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.application.ports import (
    Coach,
    FeedReply,
    FeedSource,
)

# domain
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.domain.feed_item import (  # noqa: F401
    FeedItem,
    FeedReplyPlan,
)

# integration
from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_reply_applier import (
    FeedReplyApplier,
    InMemoryReplyGuard,
    ReplyTransport,
)


def default_id_factory() -> str:
    return str(uuid.uuid4())


def default_clock_text() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_feed_reply_applier(
    *,
    transport,
    guard: Optional[InMemoryReplyGuard] = None,
) -> FeedReplyApplier:
    """Wrap a reply transport behind an idempotency guard."""
    return FeedReplyApplier(transport=transport, guard=guard or InMemoryReplyGuard())


def build_feed_runner(
    *,
    source: FeedSource,
    reply,
    coach: Coach,
    guard: Optional[InMemoryReplyGuard] = None,
    id_factory: Callable[[], str] = default_id_factory,
    ts_factory: Callable[[], str] = default_clock_text,
) -> FeedRunnerUseCase:
    """Wire the runner; ``reply`` is a transport that gets wrapped once-per-request."""
    return FeedRunnerUseCase(
        source=source,
        reply=build_feed_reply_applier(transport=reply, guard=guard),
        coach=coach,
        id_factory=id_factory,
        ts_factory=ts_factory,
    )


def build_feed_runner_from_repo(
    *,
    workspace_id: str,
    repo_root: Optional[Path] = None,
    transport: Optional[ReplyTransport] = None,
) -> FeedRunnerUseCase:  # pragma: no cover - exercised by live smoke
    """Production wiring: real Feed source/transport + the LLM coach.

    The coach is ``ClaudeCoach`` (one-shot ``claude -p``), not the deprecated
    screen-scrape ``CmuxCoachClient`` — so the feed path no longer touches
    ``mediate_decision.build_mediate_use_case_from_repo``. The dangerous-action
    safety gate runs ahead of the coach inside ``FeedRunnerUseCase`` (C003), so
    the coach stays decide-only.

    ``transport`` is an optional reply-transport seam for the live SMOKEs: they
    pass a recording wrapper around ``CmuxFeedTransport`` to prove a reply was
    (E003) or was not (C003) delivered, while still exercising the real source
    and coach. It defaults to ``CmuxFeedTransport()`` so production wiring is
    byte-identical; the builder wraps it once-per-request behind the idempotency
    guard exactly as before.
    """
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.claude_coach import (
        ClaudeCoach,
    )
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_event_source import (
        CmuxFeedSource,
    )
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_reply_applier import (
        CmuxFeedTransport,
    )

    return build_feed_runner(
        source=CmuxFeedSource(),
        reply=transport or CmuxFeedTransport(),
        coach=ClaudeCoach(),
    )


__all__ = [
    "FeedRunnerUseCase",
    "build_feed_reply_applier",
    "build_feed_runner",
    "build_feed_runner_from_repo",
]
