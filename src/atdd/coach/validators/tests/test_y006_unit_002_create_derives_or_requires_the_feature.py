# URN: test:govern-lifecycle:bind-issue-feature:Y006-UNIT-002-create-derives-or-requires-the-feature
# Acceptance: acc:govern-lifecycle:Y006-UNIT-002-create-derives-or-requires-the-feature
# WMBT: wmbt:govern-lifecycle:Y006
# Phase: RED
# Layer: application
# Runtime: python
# Assertion: behavioral
# Purpose: A newly minted issue carries a non-null stored feature — `atdd author issue` derives the URN when it can and refuses loudly when it cannot.
"""
RED Test for test:govern-lifecycle:bind-issue-feature:Y006-UNIT-002-create-derives-or-requires-the-feature
wagon: govern-lifecycle | feature: bind-issue-feature | phase: RED
WMBT: wmbt:govern-lifecycle:Y006

Purpose: the null binding must be unreachable through the sanctioned mint path.

Today `publish_issue` forwards whatever `--feature` it is given, including
``None``, and validates nothing against ``plan/``. Measured 2026-07-28: 638 of
808 stored work items carry no feature at all.

The GitHub projection is stubbed at `atdd.integrations.github.issue_state.
create_issue`, so these exercise the store decision and never touch the
network.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.author_issue import create_issue_body
from atdd.planner.commands.author_publish import PublishError, publish_issue

from ._bind_issue_feature_helpers import (
    ABSENT_FEATURE_URN,
    FEATURE_URN,
    TRAIN_URN_IN_FEATURE_SLOT,
    control_root,
    open_store,
    write_plan_tree,
)

pytestmark = [pytest.mark.platform]

# The default `create_issue_body` stamps when no feature is supplied. A minted
# issue carrying this value has not been bound — it has been decorated.
TEMPLATE_PLACEHOLDER = "feature:author-atdd-substrate:author-issue-body"


@pytest.fixture()
def stub_projection(monkeypatch):
    """No GitHub call: the store decision is what is under test."""
    import atdd.integrations.github.issue_state as issue_state

    monkeypatch.setattr(issue_state, "create_issue", lambda **kw: 99001, raising=False)
    return issue_state


def _repo(tmp_path):
    root = control_root(tmp_path)
    write_plan_tree(root)
    return root


def _stored_feature(root, slug):
    """The feature recorded for ``slug``, resolved the way production resolves it.

    A work item is keyed by a minted ``wi_<ULID>`` uid, not by its slug (#1622); the slug
    rides in ``data`` as display metadata. Fetching at ``objects.get(slug)`` finds nothing
    and reports the feature absent for an object that carries it perfectly well.
    """
    from atdd.state.work_item_writer import resolve_work_item

    store = open_store(root)
    obj = resolve_work_item(store, slug)
    return None if obj is None else (obj.data or {}).get("feature")


def test_resolving_feature_is_written_and_agrees_with_the_body(tmp_path, stub_projection) -> None:
    """A feature that resolves in plan/ lands in the store and in the body row."""
    root = _repo(tmp_path)
    body = create_issue_body({"title": "probe", "feature": FEATURE_URN})

    publish_issue("resolving-probe", body, title="probe", feature=FEATURE_URN,
                  control_root=root)

    assert _stored_feature(root, "resolving-probe") == FEATURE_URN
    assert f"| Feature | `{FEATURE_URN}` |" in body, (
        "the body's Feature row disagrees with the stored binding"
    )


def test_non_resolving_feature_is_refused_and_mints_nothing(tmp_path, stub_projection) -> None:
    """A well-formed URN naming no feature in plan/ must refuse before any write."""
    root = _repo(tmp_path)
    body = create_issue_body({"title": "probe", "feature": ABSENT_FEATURE_URN})

    with pytest.raises(PublishError) as exc:
        publish_issue("absent-probe", body, title="probe",
                      feature=ABSENT_FEATURE_URN, control_root=root)

    assert ABSENT_FEATURE_URN in str(exc.value), "the refusal does not name the URN that failed to resolve"
    assert _stored_feature(root, "absent-probe") is None, (
        "a work item was created for a feature that resolves to nothing — "
        "a half-published record"
    )


def test_omitted_feature_is_derived_or_refused_never_placeholdered(tmp_path, stub_projection) -> None:
    """No `--feature` must not silently become the template placeholder or NULL."""
    root = _repo(tmp_path)
    body = create_issue_body({"title": "probe"})

    try:
        publish_issue("omitted-probe", body, title="probe", feature=None,
                      control_root=root)
    except PublishError as exc:
        assert "feature" in str(exc).lower(), (
            "refusing an unbound mint is acceptable, but the error must name --feature"
        )
        return

    stored = _stored_feature(root, "omitted-probe")
    assert stored is not None, (
        "the mint succeeded with a NULL feature — this is the 638-of-808 status quo"
    )
    assert stored != TEMPLATE_PLACEHOLDER, (
        "the mint defaulted to the template placeholder instead of deriving a real binding"
    )


def test_a_train_urn_is_not_accepted_as_a_feature(tmp_path, stub_projection) -> None:
    """The #1626 drift: a train identity wearing a feature's clothes is refused."""
    root = _repo(tmp_path)
    body = create_issue_body({"title": "probe", "feature": TRAIN_URN_IN_FEATURE_SLOT})

    with pytest.raises(PublishError):
        publish_issue("train-urn-probe", body, title="probe",
                      feature=TRAIN_URN_IN_FEATURE_SLOT, control_root=root)

    assert _stored_feature(root, "train-urn-probe") is None
