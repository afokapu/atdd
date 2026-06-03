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
) -> FeedRunnerUseCase:  # pragma: no cover - exercised by live smoke
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_event_source import (
        CmuxFeedSource,
    )
    from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.feed_reply_applier import (
        CmuxFeedTransport,
    )
    from atdd.mediate_worker_decisions.mediate_decision.composition import (
        build_mediate_use_case_from_repo,
    )

    root = Path(repo_root or Path.cwd())
    mediate = build_mediate_use_case_from_repo(root)

    class _MediateCoach:
        """Adapt the mediate-decision use case to the runner's Coach port."""

        def mediate(self, request):
            outcome = mediate.handle(request)
            return getattr(outcome, "verdict", None)

    return build_feed_runner(
        source=CmuxFeedSource(),
        reply=CmuxFeedTransport(),
        coach=_MediateCoach(),
    )


__all__ = [
    "FeedRunnerUseCase",
    "build_feed_reply_applier",
    "build_feed_runner",
    "build_feed_runner_from_repo",
]
