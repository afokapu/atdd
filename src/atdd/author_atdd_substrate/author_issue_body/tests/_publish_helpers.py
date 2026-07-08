"""Shared helpers for the author-issue store-publish tests (#1272).

These tests anchor the E008 (publish behaviour) and C012 (publish guard)
acceptances. They are written at the RED phase: the store-first publish path
(``atdd author issue`` writing a work_item + a github external_ref, and failing
loud when the store is unreachable) does not exist yet, so every assertion below
fails for that reason and flips GREEN once the publish path lands. Nothing here
is ``assert False`` theater — each test exercises the *eventual* capability
against the real (future) public surface (``author.run`` + the State Store).

BOUNDARY: ``author-atdd-substrate`` is a ``commons``-themed wagon, so nothing in
this tree may ``import atdd.coach`` (planner.theme.commons-coach-boundary, #970).
These helpers touch only the planner author surface and the foundational
``atdd.state`` layer.
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path
from typing import Optional, Tuple

#: A github issue number the stubbed create returns (kept distinctive so a real
#: gh call could never coincidentally produce it in a hermetic run).
STUB_ISSUE_NUMBER = 987654


def run_author_issue(argv: list[str]) -> Tuple[int, str]:
    """Run ``atdd author issue …`` in-process; return ``(exit_code, stdout)``.

    Uses the real planner ``author.run`` entry point (not a subprocess) so unit
    tests can monkeypatch the github create and read the State Store directly.
    A ``SystemExit`` (argparse rejects an unknown flag pre-GREEN) is captured as
    its numeric code, so the RED failure is behavioural, not a crash.
    """
    from atdd.planner.commands import author

    buf = io.StringIO()
    code = 0
    with contextlib.redirect_stdout(buf):
        try:
            code = author.run(["issue", *argv])
        except SystemExit as exc:  # unknown --slug pre-GREEN, or a fail-loud exit
            code = exc.code if isinstance(exc.code, int) else 1
    return int(code or 0), buf.getvalue()


def open_store(control_root: Path):
    """Open the State Store under ``control_root`` (migrating if needed).

    Returns ``(StateStore, connection)`` — the caller closes the connection.
    """
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    conn = connect(init_state_store(start=control_root))
    return StateStore(conn), conn


def path_with_stub_gh(tmp_path, number: int = STUB_ISSUE_NUMBER) -> str:
    """Write a fake ``gh`` under ``tmp_path/bin`` and return a PATH prefixed with it.

    The stub drains stdin (the ``--body-file -`` body) and prints a canned issue
    URL, so a real CLI smoke exercises the store-first publish end-to-end WITHOUT
    filing a real GitHub issue (E008-SMOKE / C012-SMOKE run hermetically).
    """
    import os
    import stat

    bindir = tmp_path / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    gh = bindir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        "cat >/dev/null 2>&1 || true\n"
        f"echo 'https://github.com/afokapu/atdd/issues/{number}'\n"
    )
    gh.chmod(gh.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    return f"{bindir}{os.pathsep}{os.environ.get('PATH', '')}"


def stub_github_create(monkeypatch, number: Optional[int] = STUB_ISSUE_NUMBER) -> None:
    """Point the github issue-create primitive at a hermetic stub returning ``number``.

    ``raising=False`` so the patch also works pre-GREEN (the attribute does not
    exist until the coach-free ``integrations.github`` create primitive lands).
    """
    def _fake_create_issue(*args, **kwargs):
        return number

    monkeypatch.setattr(
        "atdd.integrations.github.issue_state.create_issue",
        _fake_create_issue,
        raising=False,
    )
