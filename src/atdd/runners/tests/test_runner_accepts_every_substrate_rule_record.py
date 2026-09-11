# URN: component:govern-lifecycle:enforcement-substrate:runner_rule_record_acceptance:backend:tests
# Runtime: python
# Purpose: The metric runner must select rules by the fields it uses, not by which of the two identically-named RuleMetadata classes built them (#1931).

"""The runner selects on capability, not on class identity (issue #1931).

Two classes named ``RuleMetadata`` exist:

* ``atdd.coach.utils.rule_binding.RuleMetadata`` — what ``find_repo_rules``
  yields when it walks ``plan/``.
* ``atdd.coach.utils.rule_id_registry.RuleMetadata`` — what ``build_registry``
  returns, and what ``metric_runner`` imports.

``_select_runnable_rules`` guarded with ``isinstance(meta, RuleMetadata)``
against the second. Repo-walked rules are the first, so feeding
``find_repo_rules`` output straight to the runner dropped every rule and
returned an empty violation list — spelled identically to a clean run.

The supported path survives only because ``build_registry`` converts between
the two while merging the repo walk. Nothing said that conversion was
load-bearing, and the same two-classes-one-name split is what produced #1925:
``rule_binding`` stringified ``signal_threshold`` while ``rule_id_registry``
documented and implemented verbatim passthrough for the identically-named
field.

The runner reads exactly four fields off a rule — ``rule_id``, ``severity``,
``signal_metric``, ``signal_threshold`` — and none of them requires a
particular class. So selection is by those fields.

Acceptance criteria (issue #1931):

* ``find_repo_rules`` output produces violations instead of silence.
* Both ``RuleMetadata`` classes are accepted.
* A record missing the fields is skipped, as before.
* A non-rule value in the registry is skipped rather than crashing.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from atdd.coach.utils.rule_binding import (
    RuleMetadata as WalkerRuleMetadata,
    find_repo_rules,
)
from atdd.coach.utils.rule_id_registry import RuleMetadata as RegistryRuleMetadata
from atdd.runners.metric_runner import (
    _select_runnable_rules,
    collect_metric_violations,
)


pytestmark = [pytest.mark.platform]


def _consumer_repo(tmp_path: Path) -> Path:
    """A repo with one metric acceptance whose metric violates its bar."""
    (tmp_path / "plan" / "slice").mkdir(parents=True)
    (tmp_path / "plan" / "slice" / "M001.yaml").write_text(
        textwrap.dedent(
            """\
            urn: "wmbt:slice:M001"
            id: "M001"
            title: "A measured outcome"
            acceptances:
              - identity:
                  urn: "acc:slice:M001-METRIC-001-over-budget"
                  id: "AC-METRIC-001"
                  purpose: "the measured value stays within its budget"
                  phase: "GREEN"
                given:
                  abstract: ["a populated fixture set"]
                when:
                  abstract: "the measurement runs"
                then:
                  abstract: ["the value is within budget"]
                signal:
                  metric: "over_budget"
                  threshold: 0
                metadata:
                  author: "atdd:self-compliance"
                  created: "2026-09-11"
            """
        ),
        encoding="utf-8",
    )
    metrics = tmp_path / ".atdd" / "metrics"
    metrics.mkdir(parents=True)
    (metrics / "over_budget.py").write_text(
        "def compute(repo_root):\n    return 7\n\n"
        "def passes(value, threshold):\n    return value <= threshold\n",
        encoding="utf-8",
    )
    return tmp_path


def test_walker_output_is_not_silently_discarded(tmp_path):
    """``find_repo_rules`` → runner must enforce, not return silence.

    The regression for #1931. An empty list here is indistinguishable from
    "nothing to enforce", which is why the drop went unnoticed: on an
    enforcement path those two states must never be spelled the same way.
    """
    repo = _consumer_repo(tmp_path)
    registry = {
        meta.rule_id: meta
        for _src, meta in find_repo_rules(repo)
        if meta.signal_metric
    }
    assert registry, "fixture must produce at least one metric-bearing rule"

    violations = collect_metric_violations(registry, repo)

    assert len(violations) == 1
    assert "over_budget" in violations[0].detail


def test_both_rulemetadata_classes_are_selected(tmp_path):
    """The two identically-named records are equally acceptable."""
    walker = WalkerRuleMetadata(
        rule_id="repo.slice.walker",
        severity=4,
        description="fixture rule",
        recipe=None,
        introduced_in=None,
        source_path=Path("/dev/null"),
        signal_metric="m",
        signal_threshold=0,
    )
    registry_rec = RegistryRuleMetadata(
        rule_id="repo.slice.registry",
        convention_path=Path("/dev/null"),
        severity=4,
        signal_metric="m",
        signal_threshold=0,
    )
    selected = _select_runnable_rules(
        {walker.rule_id: walker, registry_rec.rule_id: registry_rec}
    )
    assert {m.rule_id for m in selected} == {
        "repo.slice.walker",
        "repo.slice.registry",
    }


def test_a_record_without_the_fields_is_still_skipped():
    """Selection narrows on capability; a rule with no metric is not runnable.

    The pre-existing skips stay skips — this change widens what counts as a
    rule record, it does not widen what counts as runnable.
    """
    no_metric = RegistryRuleMetadata(
        rule_id="repo.slice.no-metric",
        convention_path=Path("/dev/null"),
        severity=4,
        signal_metric=None,
        signal_threshold=0,
    )
    no_threshold = RegistryRuleMetadata(
        rule_id="repo.slice.no-threshold",
        convention_path=Path("/dev/null"),
        severity=4,
        signal_metric="m",
        signal_threshold=None,
    )
    assert _select_runnable_rules(
        {no_metric.rule_id: no_metric, no_threshold.rule_id: no_threshold}
    ) == []


def test_a_non_rule_value_is_skipped_not_crashed_on():
    """The guard's defensive purpose survives: junk in, no exception out.

    ``isinstance`` bought crash-safety at the cost of correctness. Selecting on
    fields has to keep the safety without the cost.
    """
    class Impostor:
        rule_id = "repo.slice.impostor"

    registry = {
        "a": None,
        "b": "not a rule",
        "c": {"rule_id": "dict-shaped", "signal_metric": "m"},
        "d": Impostor(),
    }
    assert _select_runnable_rules(registry) == []
