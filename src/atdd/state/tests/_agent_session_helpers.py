"""Shared fixtures for the #1540 agent-session-identity tests.

Every helper here builds a real State Store on a tmp path — no mocks of the
store itself, because the acceptances are about what actually lands in
``objects`` / ``relationships`` / ``external_refs``.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from atdd.state.db import connect, init_state_store
from atdd.state.manifest_import import GITHUB_PROVIDER, WORK_ITEM_KIND
from atdd.state.store import StateStore

SLUG = "record-agent-session-identity-at-write-points"
ISSUE_NUMBER = 1540

# A provider table with two rows, so "adding a provider is a YAML line" is
# testable without editing the shipped table.
TWO_PROVIDER_TABLE = """
version: "1.0"
name: "test table"
providers:
  - agent: claude-code
    provider: claude
    session_env: TEST_CLAUDE_SESSION_ID
    resume_template: "cd {cwd} && claude --resume {session_id}"
  - agent: other-agent
    provider: other
    session_env: TEST_OTHER_SESSION_ID
    resume_template: "other-cli attach {session_id} --dir {cwd}"
"""


def write_provider_table(tmp_path: Path, body: str = TWO_PROVIDER_TABLE) -> Path:
    path = tmp_path / "agent_session_env.yaml"
    path.write_text(body)
    return path


def control_root(tmp_path: Path) -> Path:
    (tmp_path / ".atdd").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".atdd" / "config.yaml").write_text("version: '1.0'\n")
    return tmp_path


def open_store(root: Path) -> StateStore:
    return StateStore(connect(init_state_store(start=root)))


def seed_work_item(store: StateStore, *, slug: str = SLUG,
                   issue_number: int = ISSUE_NUMBER, state: str = "RED",
                   data: Optional[Dict[str, Any]] = None) -> str:
    """A work item linked to its github issue, as the real mint leaves it."""
    store.objects.upsert(slug, WORK_ITEM_KIND, state=state,
                         data=data or {"issue_number": issue_number})
    store.external_refs.link(slug, GITHUB_PROVIDER, "issue", str(issue_number))
    return slug
