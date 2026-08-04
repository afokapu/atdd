# URN: test:govern-lifecycle:bind-issue-train:Y008-UNIT-002-revise-writes-a-validated-train
# Acceptance: acc:govern-lifecycle:Y008-UNIT-002-revise-writes-a-validated-train
# WMBT: wmbt:govern-lifecycle:Y008
# Phase: GREEN
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: `atdd author issue --revise --train` — the non-deprecated surface — honours and validates the flag instead of refusing it by name, so a validated non-deprecated way to correct a train exists.
"""GREEN test for acc:govern-lifecycle:Y008-UNIT-002-revise-writes-a-validated-train.

wagon: govern-lifecycle | feature: bind-issue-train | WMBT: wmbt:govern-lifecycle:Y008

#1661 refused ``--revise --train`` by name, on the grounds that a revision defines
no semantics for create-time metadata. That closed the silent-ignore correctly and
left a different hole: the ONLY functional train setter was the DEPRECATED
``atdd update <N> --train``, and that one validated nothing. So the repository had
a validated command that could not set a train and an unvalidated one that could.

This exercises the whole chain the value must survive — the argparse namespace
through ``_run_issue_revise`` / ``_publish_revision`` / ``revise_issue`` /
``revise_work_item_issue`` — because a value read at the entry point and dropped
by the next hop is still dropped. That is precisely how #1635's Break 4 survived
eight measured revisions.
"""
from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

import pytest

from ._bind_issue_train_helpers import (
    ABSENT_TRAIN,
    CONSUMER_TRAIN,
    CONSUMER_TRAIN_LEGACY,
    control_root,
    open_store,
    read_issue_data,
    seed_issue,
    write_consumer_plan_tree,
)

_ISSUE = 90159
_SEED = "revise-train-probe"
_ORIGINAL_BODY = "# original body\n"


@pytest.fixture()
def revise_env(tmp_path, monkeypatch):
    """A real store + a NON-atdd plan tree, GitHub projection recorded not performed."""
    import atdd.integrations.github.issue_state as issue_state

    root = control_root(tmp_path)
    write_consumer_plan_tree(root)
    store = open_store(root)
    seed_issue(store, slug=_SEED, issue_number=_ISSUE, train=None, body=_ORIGINAL_BODY)
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
    from atdd.planner.commands.author import run

    err = io.StringIO()
    try:
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            rc = run(["issue", "--revise", str(_ISSUE), *argv])
    except SystemExit as exc:
        rc = int(exc.code or 0)
    return rc, err.getvalue()


def _body_file(root, text: str):
    from atdd.planner.commands.author import create_issue_body

    path = root / "body.md"
    path.write_text(
        create_issue_body({"title": text, "status": "INIT", "type": "bug"}),
        encoding="utf-8",
    )
    return path


def test_train_alone_is_a_valid_revision(revise_env) -> None:
    """An operator correcting only a wrong train must not be turned away."""
    root, _calls = revise_env

    rc, err = _revise("--train", CONSUMER_TRAIN)

    assert rc == 0, f"--train alone was refused (exit {rc}): {err!r}"
    assert read_issue_data(open_store(root), _ISSUE).get("train") == CONSUMER_TRAIN


def test_the_write_is_named_so_a_caller_can_tell_it_from_a_dropped_flag(revise_env) -> None:
    """Without this, a success is indistinguishable from the silent ignore."""
    _root, _calls = revise_env

    _rc, err = _revise("--train", CONSUMER_TRAIN)

    assert CONSUMER_TRAIN in err, (
        f"the revision did not name the train it set; stderr was: {err!r}"
    )
    assert "cannot honour" not in err, (
        f"the flag is still being refused rather than written: {err!r}"
    )


def test_train_with_a_body_file_writes_both(revise_env) -> None:
    root, calls = revise_env

    rc, err = _revise(
        "--train", CONSUMER_TRAIN_LEGACY,
        "--body-file", str(_body_file(root, "a revised title")),
    )

    assert rc == 0, f"exit {rc}: {err!r}"
    data = read_issue_data(open_store(root), _ISSUE)
    assert data.get("train") == CONSUMER_TRAIN_LEGACY, (
        "the train was overwritten by the body revision"
    )
    assert data.get("body") != _ORIGINAL_BODY, "the body was not revised"
    assert any(call[0] == "update_body" for call in calls), (
        f"the body revision was not projected: {calls!r}"
    )


def test_a_body_only_revision_does_not_clear_an_existing_train(revise_env) -> None:
    """``None`` means "unchanged", never "clear it" — as for feature and title."""
    root, _calls = revise_env

    _revise("--train", CONSUMER_TRAIN)
    rc, err = _revise("--body-file", str(_body_file(root, "another title")))

    assert rc == 0, f"exit {rc}: {err!r}"
    assert read_issue_data(open_store(root), _ISSUE).get("train") == CONSUMER_TRAIN, (
        "a revision naming no train cleared the existing reference"
    )


def test_an_unregistered_train_is_refused_and_writes_nothing(revise_env) -> None:
    """Fail closed. A half-applied revision is worse than none, because it looks
    written — the posture ``manifest_migration`` and ``extensions_lock`` take."""
    root, calls = revise_env

    _revise("--train", CONSUMER_TRAIN)          # a good reference to protect
    rc, err = _revise(
        "--train", ABSENT_TRAIN,
        "--body-file", str(_body_file(root, "should not land")),
    )

    assert rc != 0, f"an unregistered train exited 0: {err!r}"
    data = read_issue_data(open_store(root), _ISSUE)
    assert data.get("train") == CONSUMER_TRAIN, (
        f"a refused revision still moved the stored train to {data.get('train')!r}"
    )
    assert data.get("body") == _ORIGINAL_BODY, (
        "a refused revision still mutated the stored body — it is half-applied"
    )
    assert not any(call[0] == "update_body" for call in calls), (
        f"a refused revision still projected to GitHub: {calls!r}"
    )


def test_the_refusal_names_the_registry_and_a_candidate(revise_env) -> None:
    """The three setters must not each explain the same failure differently."""
    _root, _calls = revise_env

    _rc, err = _revise("--train", ABSENT_TRAIN)

    assert "--train" in err
    assert "plan/_trains.yaml" in err, f"the registry is not named: {err!r}"
    assert CONSUMER_TRAIN in err, f"no resolvable candidate is listed: {err!r}"


def test_train_is_no_longer_in_the_revise_refusal_set() -> None:
    """Narrowing the refusal set required wiring the writer, not reclassifying it.

    The pinning guard (Y007-UNIT-003) is what forced that: it asserts the set
    EXACTLY, so removing an entry is as visible an edit as adding one.
    """
    from atdd.planner.commands.author import _REVISE_UNSUPPORTED

    from .test_y007_unit_002_revise_refuses_the_flags_it_cannot_honour import (
        UNSUPPORTED_ON_REVISE,
    )

    assert "--train" not in UNSUPPORTED_ON_REVISE, (
        "--train is still pinned as unsupported while the revise path writes it"
    )
    assert "train" not in {dest for dest, _flag, _why in _REVISE_UNSUPPORTED}, (
        "--train is still in the command's own refusal set"
    )
    assert {dest for dest, _f, _w in _REVISE_UNSUPPORTED} == {"slug", "status", "branch"}, (
        "the refusal set holds something other than the three flags the revise "
        f"path still declines: {_REVISE_UNSUPPORTED}"
    )
