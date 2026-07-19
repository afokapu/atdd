"""Agent session identity capture at the canonical write points (issue #1540).

Records WHICH AGENT SESSION worked WHICH work_item, by reading ambient process
environment at two mandatory chokepoints — never by asking an agent, because
asking is a prompt and a prompt is non-deterministic and confabulable:

* ``atdd author issue``  -> the CREATOR   (``session_created_work_item``)
* the packaged ``post-commit`` hook -> a PARTICIPANT
  (``session_participates_in_work_item``, carrying the worktree path)

Data model — both primitives already exist, so there is NO schema migration
(#1540 Decision 6):

* the session is an ``objects`` row of kind ``agent_session``, linked to its
  provider-side id by an ``external_refs`` row of ``ref_kind='session'``. That
  table is UNIQUE ``(provider, ref_kind, ref_value)``, so a session is one row
  globally and can touch many work_items. Its ``data.last_seen_at`` is the
  recency stamp.
* participation is a ``relationships`` row, whose own ``data`` blob carries the
  ``worktree_path`` the participation was captured in. That table is UNIQUE
  ``(src_uid, dst_uid, rel_type)``, so participation is idempotent per
  (session, work_item) for free: a second commit updates recency, never adds a
  row.

NO ROLE IS EVER STORED (#1540 Decision 5). A participant is not definitionally
a worker — the documented recovery procedure has orchestrators commit inside a
worker's worktree. Orchestrator vs worker is inferred at READ time from the set
of worktree paths a session participated in; that inference is the reader's.

Naming follows ``state/hub.py``'s ``session_uses_adapter``: subject-verb-object.
``last_seen_at``, not ``last_active_at`` (#1540 Decision 7) — core observes
chokepoints and nothing else, and a blocked worker is not idle.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import yaml

from .store import StateStore

KIND_AGENT_SESSION = "agent_session"
REF_KIND_SESSION = "session"
REL_SESSION_CREATED_WORK_ITEM = "session_created_work_item"
REL_SESSION_PARTICIPATES_IN_WORK_ITEM = "session_participates_in_work_item"

PROVIDER_TABLE_PATH = Path(__file__).with_name("agent_session_env.yaml")


@dataclass(frozen=True)
class AgentSession:
    """A provider-tagged, opaque agent session identity.

    ``session_id`` is carried through verbatim: core never parses or interprets
    a provider's identifier.
    """

    provider: str
    session_id: str

    @property
    def uid(self) -> str:
        """Stable local uid for the session's ``objects`` row."""
        return f"{self.provider}:{self.session_id}"


@dataclass(frozen=True)
class SessionParticipation:
    """A session's recorded touch of one work_item, for the read projection."""

    session: AgentSession
    worktree_path: Optional[str]
    last_seen_at: Optional[str]
    created: bool
    resume_command: Optional[str]


@lru_cache(maxsize=1)
def load_provider_table(path: Optional[str] = None) -> tuple:
    """The agent-runtime → session-env-var rows, read as plain data."""
    raise NotImplementedError("GREEN: read agent_session_env.yaml")


def resolve_session(env: Optional[Mapping[str, str]] = None) -> Optional[AgentSession]:
    """Resolve the acting session from ambient environment, or ``None``.

    Returns ``None`` — never raises, never invents an identity — when no mapped
    session env var is present. A human at a plain shell is not an agent.
    """
    raise NotImplementedError("GREEN: first provider row whose session_env is set")


def record_creator(store: StateStore, work_item_uid: str,
                   session: Optional[AgentSession] = None, *,
                   now: Optional[str] = None) -> bool:
    """Record ``session`` as the creator of ``work_item_uid``.

    A no-op returning ``False`` when there is no session. Never raises: the
    operator's intent is the mint, and a failed identity write must not fail it.
    """
    raise NotImplementedError("GREEN: link session ref + creator relationship")


def record_participation(store: StateStore, work_item_uid: str,
                         session: Optional[AgentSession] = None, *,
                         worktree_path: Optional[str] = None,
                         now: Optional[str] = None) -> bool:
    """Record ``session`` as a participant in ``work_item_uid``.

    Idempotent per (session, work_item): a second call refreshes
    ``last_seen_at`` and never adds a second relationship. A no-op returning
    ``False`` when there is no session — and a no-op must leave any existing
    binding intact, never nulling what it could not observe.
    """
    raise NotImplementedError("GREEN: upsert session, stamp recency, link participation")


def sessions_for_work_item(store: StateStore, work_item_uid: str) -> List[SessionParticipation]:
    """Every session that touched ``work_item_uid``, most recently seen first.

    Ordered by ``last_seen_at`` — NOT by creation order, which misorders 32% of
    measured multi-session work_items. Asserts no role.
    """
    raise NotImplementedError("GREEN: join session refs to their relationships")


def resume_command(session: AgentSession, cwd: Optional[str]) -> Optional[str]:
    """The provider's runnable resume command, from its ``resume_template``."""
    raise NotImplementedError("GREEN: render the provider's resume_template")
