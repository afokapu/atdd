"""Tests for non-lifecycle issue skip in test_issue_advancement.

A PR whose linked issue carries a `tracking` / `meta` / `epic` / `parent`
label should NOT trigger advancement enforcement, because such issues don't
advance through the 6-phase lifecycle — their state is the cumulative state
of their child issues.
"""
from atdd.coach.validators.test_issue_advancement import (
    _NON_LIFECYCLE_LABELS,
    _issue_is_non_lifecycle,
)


class TestIssueIsNonLifecycle:
    def test_returns_true_for_tracking_label(self):
        issue = {"labels": [{"name": "tracking"}, {"name": "atdd:INIT"}]}
        assert _issue_is_non_lifecycle(issue) is True

    def test_returns_true_for_meta_label(self):
        issue = {"labels": [{"name": "meta"}]}
        assert _issue_is_non_lifecycle(issue) is True

    def test_returns_true_for_epic_label(self):
        issue = {"labels": [{"name": "epic"}]}
        assert _issue_is_non_lifecycle(issue) is True

    def test_returns_true_for_parent_label(self):
        issue = {"labels": [{"name": "parent"}]}
        assert _issue_is_non_lifecycle(issue) is True

    def test_returns_false_for_normal_lifecycle_issue(self):
        issue = {"labels": [{"name": "atdd:INIT"}, {"name": "archetype:coach"}]}
        assert _issue_is_non_lifecycle(issue) is False

    def test_returns_false_for_no_labels(self):
        assert _issue_is_non_lifecycle({"labels": []}) is False
        assert _issue_is_non_lifecycle({}) is False

    def test_returns_false_for_label_with_similar_substring(self):
        # "tracking-misc" should NOT trip the "tracking" exact match.
        issue = {"labels": [{"name": "tracking-misc"}, {"name": "atdd:RED"}]}
        assert _issue_is_non_lifecycle(issue) is False

    def test_handles_string_labels_legacy_shape(self):
        issue = {"labels": ["tracking"]}
        assert _issue_is_non_lifecycle(issue) is True

    def test_returns_true_when_one_of_many_labels_is_non_lifecycle(self):
        issue = {"labels": [
            {"name": "atdd:INIT"},
            {"name": "tracking"},
            {"name": "archetype:coach"},
        ]}
        assert _issue_is_non_lifecycle(issue) is True


class TestNonLifecycleLabelsConst:
    def test_includes_documented_labels(self):
        assert _NON_LIFECYCLE_LABELS == frozenset({"tracking", "meta", "epic", "parent"})

    def test_is_immutable(self):
        # frozenset by contract — mutation should fail
        import pytest
        with pytest.raises((AttributeError, TypeError)):
            _NON_LIFECYCLE_LABELS.add("foo")  # type: ignore[attr-defined]
