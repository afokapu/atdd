# URN: test:govern-lifecycle:bind-issue-train:Y008-UNIT-001-create-rejects-an-unregistered-train
# Acceptance: acc:govern-lifecycle:Y008-UNIT-001-create-rejects-an-unregistered-train
# WMBT: wmbt:govern-lifecycle:Y008
# Phase: GREEN
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: The create path refuses a train the repository does not register BEFORE the store connection opens, so a refused mint leaves no half-published record.
"""GREEN test for acc:govern-lifecycle:Y008-UNIT-001-create-rejects-an-unregistered-train.

wagon: govern-lifecycle | feature: bind-issue-train | WMBT: wmbt:govern-lifecycle:Y008

The guard is placed where the feature guard already is — before
``init_state_store`` — because a refusal AFTER the store write is not a refusal,
it is a rollback nobody wrote. The assertion that the work item does not exist
afterwards is what distinguishes the two, and it is the reason this test seeds no
work item of its own.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.author_publish import PublishError, publish_issue
from atdd.state.manifest_import import WORK_ITEM_KIND

from ._bind_issue_train_helpers import (
    ABSENT_TRAIN,
    CONSUMER_FEATURE,
    CONSUMER_TRAIN,
    CONSUMER_TRAIN_LEGACY,
    control_root,
    open_store,
    write_consumer_plan_tree,
)


@pytest.fixture()
def mint_env(tmp_path, monkeypatch):
    """A real store + a NON-atdd plan tree, with the GitHub projection RECORDED.

    ``create_issue`` is patched on the module ``publish_issue`` imports it from,
    not on ``author_publish`` — the import is inside the try block, so patching
    the caller's namespace would silently do nothing and let the test reach the
    real provider. It raises rather than returning a number, which drives the
    publish down its outbox path: no network, and the store work item still
    stands, which is the condition these assertions read.
    """
    import atdd.integrations.github.issue_state as issue_state

    root = control_root(tmp_path)
    write_consumer_plan_tree(root)

    created: list = []

    def _fake_create(**kwargs):
        created.append(kwargs)
        raise RuntimeError("no provider in this test — the outbox path is expected")

    monkeypatch.setattr(issue_state, "create_issue", _fake_create)
    monkeypatch.chdir(root)
    return root, created


def _mint(root, slug, train):
    return publish_issue(
        slug,
        f"# {slug}\n",
        title=slug,
        status="INIT",
        issue_type="implementation",
        train=train,
        feature=CONSUMER_FEATURE,
        control_root=root,
    )


def _stored_train(root, slug):
    obj = open_store(root).objects.get(slug)
    return None if obj is None else (obj.data or {}).get("train")


def test_a_registered_canonical_train_is_written(mint_env) -> None:
    root, created = mint_env

    _mint(root, "registered-train", CONSUMER_TRAIN)

    assert _stored_train(root, "registered-train") == CONSUMER_TRAIN
    assert created, (
        "the projection seam was never reached, so this test's stub is not the "
        "one the publish path calls and the mint may have gone somewhere real"
    )


def test_a_resolvable_alias_is_accepted(mint_env) -> None:
    """An operator is not made to migrate a legacy spelling before recording lineage.

    27 of the live corpus's train references are legacy ids, and they resolve only
    through ``plan/_trains/_aliases.yaml``. Refusing them would turn a working
    reference into a blocked mint.
    """
    root, _created = mint_env

    _mint(root, "alias-train", CONSUMER_TRAIN_LEGACY)

    assert _stored_train(root, "alias-train") == CONSUMER_TRAIN_LEGACY, (
        "the alias was rewritten on the way in; the setter validates a reference, "
        "it does not migrate one"
    )


def test_an_unregistered_train_is_refused(mint_env) -> None:
    root, _created = mint_env

    with pytest.raises(PublishError) as excinfo:
        _mint(root, "unregistered-train", ABSENT_TRAIN)

    message = str(excinfo.value)
    assert "--train" in message, (
        f"the refusal does not name the input that caused it: {message!r}"
    )
    assert "plan/_trains.yaml" in message, (
        f"the refusal does not name the registry consulted: {message!r}"
    )
    assert CONSUMER_TRAIN in message, (
        f"the refusal lists no candidate that would have resolved: {message!r}"
    )


def test_a_refused_mint_writes_no_work_item(mint_env) -> None:
    """The guard runs before the store write, not after it.

    This is the assertion that makes the placement load-bearing: a guard that
    fired after ``create_work_item`` would leave exactly the half-published record
    that #1271 was about.
    """
    root, created = mint_env

    with pytest.raises(PublishError):
        _mint(root, "refused-mint", ABSENT_TRAIN)

    store = open_store(root)
    assert store.objects.get("refused-mint") is None, (
        "a refused mint left a work item behind — the train guard runs after the "
        "store write, so the refusal is a rollback nobody wrote"
    )
    assert not created, (
        f"a refused mint still attempted a GitHub projection: {created!r}"
    )


def test_a_placeholder_train_is_refused(mint_env) -> None:
    """"TBD" is what 11 live work items carry. The setter is where that stops."""
    root, _created = mint_env

    with pytest.raises(PublishError) as excinfo:
        _mint(root, "placeholder-train", "TBD")

    assert "not a train identity" in str(excinfo.value)


def test_a_mint_naming_no_train_is_accepted(mint_env) -> None:
    """A train is optional for the issue types that do not require one.

    Unlike ``--feature``, nothing is derived from the body and nothing is
    required: 481 of the live non-terminal work items carry no train at all, and
    the guard must cost them nothing.
    """
    root, _created = mint_env

    _mint(root, "no-train", None)

    obj = open_store(root).objects.get("no-train")
    assert obj is not None, "a mint naming no train was refused"
    assert obj.kind == WORK_ITEM_KIND
    assert (obj.data or {}).get("train") is None
