# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:Y007-UNIT-001-revise-writes-the-title-to-store-and-github
# Acceptance: acc:govern-lifecycle:Y007-UNIT-001-revise-writes-the-title-to-store-and-github
# WMBT: wmbt:govern-lifecycle:Y007
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: `atdd author issue --revise <N> --title <t>` writes the title onto the authoritative work item and projects it to the GitHub issue title instead of accepting the flag and discarding it.
"""
RED Test for test:govern-lifecycle:issue-author-validate-locally-publish-once:Y007-UNIT-001-revise-writes-the-title-to-store-and-github
wagon: govern-lifecycle | feature: issue-author-validate-locally-publish-once | phase: RED
WMBT: wmbt:govern-lifecycle:Y007

Purpose: the revise path must carry `--title` all the way into the store and on
to the GitHub issue title.

Measured 2026-08-02 against the tree at 84c46b4c: `--revise <N> --title X --type
bug` exits 0 with `objects.data.title` unchanged and zero GitHub title calls,
and `--revise <N> --body-file f --title X` writes the body — whose H1 carries
the new title — while the GitHub title stays stale. That is the divergence
#1636 needed an operator's `gh issue edit` to repair. Statically, `args.title`
is read at three lines in ``author.py`` and all three are inside
``_run_issue_create``.

Fails today because ``revise_work_item_issue`` has no ``title`` parameter and
nothing on the revise path calls a GitHub title update — a behavioural
assertion on stored state and recorded calls, not an import error.
"""
from __future__ import annotations

import inspect

import pytest

from atdd.state.work_item_writer import revise_work_item_issue

from ._bind_issue_feature_helpers import (
    control_root,
    open_store,
    read_issue_data,
    seed_issue,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

_ISSUE = 94071
_STALE = "the stale title the github issue still carries"
_FRESH = "the title the caller asked for"


@pytest.fixture()
def revise_env(tmp_path, monkeypatch):
    """A real store + plan tree, with the GitHub projection recorded not performed.

    Returns ``(root, calls)`` where ``calls`` accumulates ``(op, issue, value)``
    for every projection the revise path attempts. Recording rather than
    stubbing-to-nothing is the point: the acceptance is that a title update is
    *issued*, and a silent no-op is exactly the defect under test.
    """
    import atdd.integrations.github.issue_state as issue_state

    root = control_root(tmp_path)
    write_plan_tree(root)
    store = open_store(root)
    seed_issue(store, slug="revise-title-probe", issue_number=_ISSUE,
               feature=None, body=f"# {_STALE}\n")
    store.conn.commit()
    store.conn.close()

    calls: list[tuple[str, int, str]] = []
    monkeypatch.setattr(
        issue_state, "update_body",
        lambda n, b: calls.append(("body", n, b)), raising=False,
    )
    monkeypatch.setattr(
        issue_state, "update_title",
        lambda n, t: calls.append(("title", n, t)), raising=False,
    )
    monkeypatch.chdir(root)
    return root, calls


def _revise(root, *argv: str) -> int:
    """Run the real CLI revise path in-process; return its exit code."""
    from atdd.planner.commands.author import run

    try:
        return run(["issue", "--revise", str(_ISSUE), *argv])
    except SystemExit as exc:  # argparse refusals surface this way
        return int(exc.code or 0)


def _stored_title(root) -> str:
    store = open_store(root)
    try:
        return read_issue_data(store, _ISSUE).get("title")
    finally:
        store.conn.close()


def _body_file(root, title: str):
    """A schema-valid body whose H1 is ``title``."""
    from atdd.planner.commands.author import create_issue_body

    path = root / "body.md"
    path.write_text(
        create_issue_body({"title": title, "status": "INIT", "type": "bug"}),
        encoding="utf-8",
    )
    return path


def test_title_alone_is_a_valid_revision(revise_env) -> None:
    """`--title` on its own is a revision, not a request missing its payload.

    The precondition today demands --body-file, --feature and/or --type, so an
    operator correcting only a wrong title is turned away — and when they
    satisfy it by also passing --type, the title is dropped further down.
    """
    root, _calls = revise_env

    rc = _revise(root, "--title", _FRESH)

    assert rc == 0, (
        f"`--revise --title` exited {rc}: a title correction is a complete "
        f"revision and must not be refused for lacking --body-file/--feature/--type"
    )
    assert _stored_title(root) == _FRESH, (
        "revise accepted a title and did not persist it — the measured silent drop"
    )


def test_title_alongside_a_body_writes_both(revise_env) -> None:
    """Neither field overwrites the other when both are supplied."""
    root, _calls = revise_env
    path = _body_file(root, _FRESH)

    rc = _revise(root, "--body-file", str(path), "--title", _FRESH)

    assert rc == 0, f"revise with --body-file and --title exited {rc}"
    data = read_issue_data(open_store(root), _ISSUE)
    assert data.get("title") == _FRESH, (
        "the title was dropped when a body accompanied it — this is #1636: the "
        "body H1 moves and the issue title stays stale"
    )
    assert data.get("body", "").startswith(f"# {_FRESH}"), (
        "the body was dropped when a title accompanied it"
    )


def test_revision_without_a_title_never_clears_the_existing_one(revise_env) -> None:
    """A body-only revision must leave the stored title untouched."""
    root, _calls = revise_env
    path = _body_file(root, "some other heading")

    rc = _revise(root, "--body-file", str(path))

    assert rc == 0, f"body-only revise exited {rc}"
    assert _stored_title(root) == "revise-title-probe", (
        "a revision naming no title overwrote or cleared the existing one; "
        "None must mean 'unchanged', never 'clear it'"
    )


def test_a_title_revision_projects_to_the_github_issue_title(revise_env) -> None:
    """The store write is not enough: the GitHub issue title must move too."""
    root, calls = revise_env

    _revise(root, "--title", _FRESH)

    titles = [c for c in calls if c[0] == "title"]
    assert titles, (
        "no GitHub title update was issued for a revision carrying --title, so "
        "the stored title and the live issue title diverge — the state that "
        "needed a manual `gh issue edit` on #1636"
    )
    assert titles[0][1] == _ISSUE and titles[0][2] == _FRESH, (
        f"the title projection carried {titles[0][1:]!r}, expected "
        f"({_ISSUE!r}, {_FRESH!r})"
    )


def test_a_failed_title_projection_is_deferred_not_lost(revise_env, monkeypatch) -> None:
    """A title projection that fails defers to the outbox, as the body already does.

    The store write is authoritative and must stand; the projection is
    best-effort with durable retry. Losing the projection silently would
    recreate the divergence this acceptance closes.
    """
    import atdd.integrations.github.issue_state as issue_state

    root, _calls = revise_env

    def boom(_n, _t):
        raise RuntimeError("GraphQL rate limit exhausted (simulated)")

    monkeypatch.setattr(issue_state, "update_title", boom, raising=False)

    rc = _revise(root, "--title", _FRESH)

    assert rc == 0, f"a deferred projection must not fail the store write (exit {rc})"
    assert _stored_title(root) == _FRESH, (
        "the authoritative store write did not stand when the projection failed"
    )
    store = open_store(root)
    rows = store.conn.execute("SELECT * FROM outbox").fetchall()
    assert rows, (
        "the failed title projection was neither performed nor enqueued — it was "
        "dropped, which is the class of defect this WMBT exists to close"
    )


def test_the_store_writer_can_receive_a_title() -> None:
    """The seam that carries the value must have a parameter for it.

    Asserted as a signature check so the RED failure names the missing
    parameter rather than surfacing a TypeError from a keyword the writer
    cannot accept.
    """
    accepted = set(inspect.signature(revise_work_item_issue).parameters)
    assert "title" in accepted, (
        "`--title` is accepted by `atdd author issue --revise` but "
        "revise_work_item_issue has no `title` parameter, so the value is "
        "discarded between the CLI and the store"
    )
