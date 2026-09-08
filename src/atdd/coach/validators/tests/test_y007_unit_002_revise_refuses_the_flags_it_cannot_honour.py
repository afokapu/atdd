# URN: test:govern-lifecycle:issue-author-validate-locally-publish-once:Y007-UNIT-002-revise-refuses-the-flags-it-cannot-honour
# Acceptance: acc:govern-lifecycle:Y007-UNIT-002-revise-refuses-the-flags-it-cannot-honour
# WMBT: wmbt:govern-lifecycle:Y007
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: A flag whose semantics the revise path does not define is refused with a non-zero exit naming that flag, rather than accepted and discarded.
"""
RED Test for test:govern-lifecycle:issue-author-validate-locally-publish-once:Y007-UNIT-002-revise-refuses-the-flags-it-cannot-honour
wagon: govern-lifecycle | feature: issue-author-validate-locally-publish-once | phase: RED
WMBT: wmbt:govern-lifecycle:Y007

Purpose: close the "write it or refuse it" half of the contract.

`--title` is written (Y007-UNIT-001). The remaining four unread flags on the
revise path — `--slug`, `--status`, `--branch`, `--train` — have no defined
revise semantics: `--slug` is the object uid, `--status` belongs to the phase
machine via `atdd coach transition`, and `--branch`/`--train` are create-time
metadata. Inventing semantics for them would be scope; accepting and dropping
them is the defect. So they are refused, loudly, naming the flag.

This matches the fail-closed posture the repo already takes elsewhere:
`manifest_migration` refuses a whole run rather than write a half-valid corpus,
and `extensions_lock` aborts before opening the file because a half-written
lock looks pinned. A flag accepted and discarded looks written.

Fails today because all four exit 0 and change nothing.
"""
from __future__ import annotations

import pytest

from ._bind_issue_feature_helpers import (
    control_root,
    open_store,
    read_issue_data,
    seed_issue,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

_ISSUE = 94072
_SEED_TITLE = "revise-refusal-probe"

# The flags the revise path declares no semantics for, and the reason each is
# refused rather than written. Kept as data so the refusal set is one list, and
# so Y007-UNIT-003 can assert this is exactly the set the guard tolerates.
UNSUPPORTED_ON_REVISE: dict[str, str] = {
    "--slug": "the work item's uid, which a revision does not move",
    "--status": "owned by the phase machine",
    "--branch": "create-time metadata",
    "--train": "create-time metadata",
}


@pytest.fixture()
def revise_env(tmp_path, monkeypatch):
    """A real store + plan tree with the GitHub projection recorded, not performed."""
    import atdd.integrations.github.issue_state as issue_state

    root = control_root(tmp_path)
    write_plan_tree(root)
    store = open_store(root)
    seed_issue(store, slug=_SEED_TITLE, issue_number=_ISSUE, feature=None,
               body="# original body\n")
    store.conn.commit()
    store.conn.close()

    calls: list = []
    for name in ("update_body", "update_title"):
        monkeypatch.setattr(
            issue_state, name,
            lambda n, v, _n=name: calls.append((_n, n, v)), raising=False,
        )
    monkeypatch.chdir(root)
    return root, calls


def _revise(*argv: str) -> tuple[int, str]:
    """Run the revise path in-process; return ``(exit_code, stderr)``."""
    import io
    from contextlib import redirect_stderr, redirect_stdout

    from atdd.planner.commands.author import run

    err = io.StringIO()
    try:
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = run(["issue", "--revise", str(_ISSUE), *argv])
    except SystemExit as exc:
        rc = int(exc.code or 0)
    return rc, err.getvalue()


@pytest.mark.parametrize("flag", sorted(UNSUPPORTED_ON_REVISE))
def test_an_unhonoured_flag_is_refused_by_name(revise_env, flag) -> None:
    """The command exits non-zero and its stderr names the offending flag."""
    _root, _calls = revise_env

    rc, err = _revise("--type", "bug", flag, "some-value")

    assert rc != 0, (
        f"`--revise {flag}` exited 0. The revise path reads nothing from "
        f"{flag}, so exit 0 reports a write that did not happen"
    )
    assert flag in err, (
        f"the refusal did not name {flag}. A caller must learn which input was "
        f"not honoured; stderr was: {err!r}"
    )


@pytest.mark.parametrize("flag", sorted(UNSUPPORTED_ON_REVISE))
def test_a_refused_revision_writes_nothing(revise_env, flag) -> None:
    """No partial write survives a refusal — fail closed, like manifest_migration.

    The companion `--type` is deliberately a DIFFERENT value from the seeded
    one. Passing the value already stored would make this assertion pass
    whether or not the write was suppressed, which proves nothing.
    """
    root, calls = revise_env

    _revise("--type", "refactor", flag, "some-value")

    data = read_issue_data(open_store(root), _ISSUE)
    assert data.get("type") == "bug", (
        f"a revision refused for {flag} still applied its --type: the stored "
        f"type moved to {data.get('type')!r}. A half-applied revision is worse "
        f"than none, because it looks written"
    )
    assert data.get("body") == "# original body\n", (
        f"a revision refused for {flag} still mutated the stored body"
    )
    assert not calls, (
        f"a revision refused for {flag} still projected to GitHub: {calls!r}"
    )


def test_the_status_refusal_names_the_command_that_owns_it(revise_env) -> None:
    """Redirect the caller, do not merely block them.

    `--status` is the one unsupported flag with a real home: the phase machine.
    A refusal that does not say so sends the caller looking for a bug.
    """
    _root, _calls = revise_env

    _rc, err = _revise("--type", "bug", "--status", "RED")

    assert "atdd coach transition" in err, (
        "the --status refusal does not name `atdd coach transition` as the "
        f"command that does own phase changes; stderr was: {err!r}"
    )


def test_a_revision_using_only_honoured_flags_is_not_refused(revise_env) -> None:
    """The guard must cost the working paths nothing.

    `--body-file` is the flag that reaches GitHub today (measured 2026-08-02).
    A refusal check that caught it too would break the one path that works.
    """
    root, _calls = revise_env
    from atdd.planner.commands.author import create_issue_body

    path = root / "body.md"
    path.write_text(
        create_issue_body({"title": "a fresh title", "status": "INIT", "type": "bug"}),
        encoding="utf-8",
    )

    rc, err = _revise("--body-file", str(path), "--type", "bug")

    assert rc == 0, (
        f"a revision using only honoured flags was refused (exit {rc}): {err!r}"
    )
