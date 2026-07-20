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

import logging
import os
import shlex
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import yaml

from .db import connect, init_state_store
from .store import StateStore

#: Kept as a literal rather than imported from ``manifest_import`` so this
#: module's transitive import surface stays as small as the boundary check
#: (``core-no-provider``) wants it. It is the kind named in the schema DDL.
WORK_ITEM_KIND = "work_item"

logger = logging.getLogger(__name__)

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


@dataclass(frozen=True)
class ProviderRow:
    """One row of the provider table. Every provider-specific string lives here."""

    agent: str
    provider: str
    session_env: str
    resume_template: Optional[str] = None


@lru_cache(maxsize=4)
def _load_table(path_str: str) -> tuple:
    """Parse one provider table. Cached on the RESOLVED path, deliberately.

    Caching on the *argument* instead would key every default call under
    ``None``, so a table read once would be served forever even after
    ``PROVIDER_TABLE_PATH`` changed — the shipped table silently replaced by
    whichever one happened to be read first.
    """
    source = Path(path_str)
    try:
        raw = yaml.safe_load(source.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        # An unreadable table means we cannot identify anyone — which is the
        # same situation as a human at a shell, and is handled the same way.
        # Logged, not silent: capture failing closed is invisible by nature, so
        # the log line is the only way anyone learns the table stopped loading.
        logger.warning(
            "agent session provider table unreadable; identity capture disabled",
            extra={"path": path_str, "error": str(exc)},
        )
        return ()
    rows = []
    for entry in raw.get("providers") or []:
        if not entry.get("session_env") or not entry.get("provider"):
            continue
        rows.append(ProviderRow(
            agent=entry.get("agent", ""),
            provider=entry["provider"],
            session_env=entry["session_env"],
            resume_template=entry.get("resume_template"),
        ))
    return tuple(rows)


def load_provider_table(path: Optional[str] = None) -> tuple:
    """The agent-runtime → session-env-var rows, read as plain data."""
    return _load_table(str(Path(path) if path else PROVIDER_TABLE_PATH))


#: The cache lives on the resolved-path helper; expose the usual handle.
load_provider_table.cache_clear = _load_table.cache_clear


def _row_for_provider(provider: str) -> Optional[ProviderRow]:
    for row in load_provider_table():
        if row.provider == provider:
            return row
    return None


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve_session(env: Optional[Mapping[str, str]] = None) -> Optional[AgentSession]:
    """Resolve the acting session from ambient environment, or ``None``.

    Returns ``None`` — never raises, never invents an identity — when no mapped
    session env var is present. A human at a plain shell is not an agent.

    First matching row wins, so the table's order is its precedence.
    """
    environ = os.environ if env is None else env
    for row in load_provider_table():
        value = environ.get(row.session_env)
        if value:
            # carried through opaque: never parsed, never validated in shape
            return AgentSession(provider=row.provider, session_id=value)
    return None


def record_creator(store: StateStore, work_item_uid: str,
                   session: Optional[AgentSession] = None, *,
                   now: Optional[str] = None) -> bool:
    """Record ``session`` as the creator of ``work_item_uid``.

    A no-op returning ``False`` when there is no session. Never raises: the
    operator's intent is the mint, and a failed identity write must not fail it.
    """
    session = session or resolve_session()
    if session is None:
        return False
    _upsert_session(store, session, now=now or _now())
    store.relationships.add(session.uid, work_item_uid, REL_SESSION_CREATED_WORK_ITEM)
    return True


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
    session = session or resolve_session()
    if session is None:
        # Observed nothing. Touch nothing: a human commit on a worker's branch
        # must not erase the worker's binding or disturb its recency.
        return False
    _upsert_session(store, session, now=now or _now())
    data: Dict[str, Any] = {}
    if worktree_path:
        data["worktree_path"] = str(worktree_path)
    # UNIQUE (src_uid, dst_uid, rel_type) makes this idempotent per
    # (session, work_item): a second commit updates, never appends.
    store.relationships.add(
        session.uid, work_item_uid, REL_SESSION_PARTICIPATES_IN_WORK_ITEM, data=data
    )
    return True


def _upsert_session(store: StateStore, session: AgentSession, *, now: str) -> None:
    """Ensure the session object + its provider ref exist, and stamp recency.

    Merges into the ref's existing ``data`` rather than replacing it, and does
    not touch ``created_at`` — the ON CONFLICT clause updates only object_uid
    and data, so the session's identity anchor survives every re-commit.
    """
    store.objects.upsert(session.uid, KIND_AGENT_SESSION)
    existing = store.external_refs.resolve(
        session.provider, REF_KIND_SESSION, session.session_id
    )
    data = dict(existing.data or {}) if existing else {}
    data["last_seen_at"] = now  # exactly one value; no history accumulates
    store.external_refs.link(
        session.uid, session.provider, REF_KIND_SESSION, session.session_id, data=data
    )


def capture_post_commit(control_root: Optional[Path] = None, *,
                        env: Optional[Mapping[str, str]] = None,
                        cwd: Optional[str] = None,
                        branch: Optional[str] = None) -> bool:
    """Entry point the packaged ``post-commit`` hook execs (#1492 dispatcher).

    The hook file under ``.atdd/hooks/`` is fixed content that only execs this;
    the logic lives in the installed package and propagates by ``pipx upgrade``.
    Editing a hook file in the repo changes nothing.

    ``post-commit``, not ``pre-commit``: it survives ``git commit --no-verify``
    and runs after the commit exists, so a store failure CANNOT block it. This
    function must therefore never raise — it returns ``False`` and leaves the
    store untouched on any fault.
    """
    try:
        environ = os.environ if env is None else env
        session = resolve_session(environ)
        if session is None:
            return False  # a human commit

        work_dir = cwd or os.getcwd()
        branch_name = branch or _current_branch(work_dir)
        if not branch_name:
            return False

        root = control_root or environ.get("ATDD_CONTROL_ROOT") or work_dir
        conn = connect(init_state_store(start=Path(root)))
        try:
            store = StateStore(conn)
            work_item_uid = _work_item_for_branch(store, branch_name)
            if work_item_uid is None:
                return False  # a branch with no registered work item
            recorded = record_participation(
                store, work_item_uid, session, worktree_path=work_dir
            )
            conn.commit()
            return recorded
        finally:
            conn.close()
    except Exception as exc:
        # The commit already exists. Nothing here is worth failing it for — but
        # it IS worth saying, or a permanently broken capture looks identical to
        # a machine with no agents on it.
        logger.warning(
            "post-commit agent session capture failed; the commit stands",
            extra={"branch": branch, "error": str(exc)},
        )
        return False


def _current_branch(cwd: str) -> Optional[str]:
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=cwd, capture_output=True, text=True,
        )
    except OSError as exc:
        logger.warning(
            "could not resolve the current branch; skipping session capture",
            extra={"cwd": cwd, "error": str(exc)},
        )
        return None
    name = proc.stdout.strip()
    return name or None


def _work_item_for_branch(store: StateStore, branch: str) -> Optional[str]:
    """Resolve branch → work_item uid via the binding E007 wrote at create."""
    for obj in store.objects.list(kind=WORK_ITEM_KIND):
        if (obj.data or {}).get("branch") == branch:
            return obj.uid
    return None


def sessions_for_work_item(store: StateStore, work_item_uid: str) -> List[SessionParticipation]:
    """Every session that touched ``work_item_uid``, most recently seen first.

    Ordered by ``last_seen_at`` — NOT by creation order, which misorders 32% of
    measured multi-session work_items. Asserts no role.

    Reads the store and the provider table only: no multiplexer, no subprocess.
    """
    refs = {
        r.object_uid: r
        for r in store.external_refs.all()
        if r.ref_kind == REF_KIND_SESSION
    }

    touched: Dict[str, Dict[str, Any]] = {}
    for rel in store.relationships.list(dst_uid=work_item_uid):
        if rel.rel_type not in (
            REL_SESSION_CREATED_WORK_ITEM, REL_SESSION_PARTICIPATES_IN_WORK_ITEM
        ):
            continue
        entry = touched.setdefault(rel.src_uid, {"created": False, "worktree_path": None})
        if rel.rel_type == REL_SESSION_CREATED_WORK_ITEM:
            entry["created"] = True
        else:
            entry["worktree_path"] = (rel.data or {}).get("worktree_path")

    rows: List[SessionParticipation] = []
    for uid, entry in touched.items():
        ref = refs.get(uid)
        if ref is None:
            continue
        session = AgentSession(provider=ref.provider, session_id=ref.ref_value)
        rows.append(SessionParticipation(
            session=session,
            worktree_path=entry["worktree_path"],
            last_seen_at=(ref.data or {}).get("last_seen_at"),
            created=entry["created"],
            resume_command=resume_command(session, entry["worktree_path"]),
        ))

    rows.sort(key=lambda r: r.last_seen_at or "", reverse=True)
    return rows


def resume_command(session: AgentSession, cwd: Optional[str]) -> Optional[str]:
    """The provider's runnable resume command, from its ``resume_template``.

    Both substitutions are shell-quoted, so a worktree path containing a space
    arrives as ONE argument. ``shlex.quote`` leaves ordinary paths untouched,
    so the common case stays readable.
    """
    row = _row_for_provider(session.provider)
    if row is None or not row.resume_template:
        return None
    return row.resume_template.format(
        session_id=shlex.quote(session.session_id),
        cwd=shlex.quote(cwd or ""),
    )
