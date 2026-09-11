# URN: component:govern-lifecycle:enforcement-substrate:authored_threshold_passthrough:backend:tests
# Runtime: python
# Purpose: Cover the walker→registry→runner SEAM for issue #1925 — the authored threshold must survive the trip to passes() with its type intact, and an unevaluatable threshold must fail closed.

"""The authored threshold reaches ``passes()`` intact (issue #1925).

These tests exist because the defect they pin lived precisely where no
test looked. Both halves of the path were individually well covered and
individually correct:

* ``test_metric_runner_unit.py`` constructs every registry entry with
  ``signal_threshold=0`` as an ``int`` — the runner is correct, and proves it.
* ``test_repo_rule_walker.py`` asserted ``signal_threshold == "0"`` — the
  walker was internally consistent, and proved it.

Nothing composed them. ``_passthrough_threshold`` returned ``str(val)``, so a
YAML ``threshold: 0`` arrived as ``'0'``, ``passes(22, '0')`` raised
``TypeError``, and the runner logged a warning and skipped — reporting a clean
gate over an acceptance it had never actually judged. 28 tests passed over a
broken composition.

So every test here starts from YAML on disk and ends at a gate verdict. A test
that starts from a hand-built ``RuleMetadata`` cannot see this class of bug,
which is the whole lesson of #1925.

Acceptance criteria (issue #1925):

* An authored ``threshold: 0`` reaches ``passes()`` as ``int`` ``0``.
* A float threshold (the rate-shaped case: ``0.02``) survives as ``float``.
* A violating metric produces a ``Violation`` end to end, from YAML.
* A ``passes()`` that raises produces a ``Violation`` — fail closed.
* A metric-only acceptance is measurable with no ``harness`` block at all.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Dict

import pytest

from atdd.coach.utils.rule_id_registry import RuleMetadata
from atdd.runners.metric_runner import build_registry, collect_metric_violations


pytestmark = [pytest.mark.platform]


_WMBT = textwrap.dedent(
    """\
    urn: "wmbt:inference-slice:M001"
    id: "M001"
    title: "Document event extraction stays within an error budget"
    dimension: likelihood
    acceptances:
      - identity:
          urn: "acc:inference-slice:M001-METRIC-001-{slug}"
          id: "AC-METRIC-001"
          purpose: "{purpose}"
          phase: "GREEN"
        given:
          abstract:
            - "a golden fixture set of labelled documents"
        when:
          abstract: "the extractor runs over every fixture"
        then:
          abstract:
            - "the measured rate is within the declared budget"
        signal:
          metric: "{metric}"
          threshold: {threshold}
        metadata:
          author: "atdd:self-compliance"
          created: "2026-09-10"
    """
)

_METRIC = textwrap.dedent(
    """\
    def compute(repo_root):
        return {value}

    def passes(value, threshold):
        {body}
    """
)


def _consumer_repo(
    tmp_path: Path,
    *,
    metric: str,
    threshold: str,
    value: str,
    passes_body: str = "return value <= threshold",
    slug: str = "wrong-extraction-rate",
    purpose: str = "the wrong-extraction rate stays within its budget",
) -> Path:
    """Write a minimal consumer repo: one WMBT acceptance + one metric module.

    *threshold* and *value* are Python/YAML source fragments, not values, so a
    test can author ``0`` and assert the ``int`` survives rather than asserting
    against something this helper already coerced.
    """
    (tmp_path / "plan" / "inference_slice").mkdir(parents=True)
    (tmp_path / "plan" / "inference_slice" / "M001.yaml").write_text(
        _WMBT.format(slug=slug, purpose=purpose, metric=metric, threshold=threshold),
        encoding="utf-8",
    )
    metrics_dir = tmp_path / ".atdd" / "metrics"
    metrics_dir.mkdir(parents=True)
    (metrics_dir / f"{metric}.py").write_text(
        _METRIC.format(value=value, body=passes_body), encoding="utf-8"
    )
    return tmp_path


def _registry(repo: Path) -> Dict[str, RuleMetadata]:
    """Harvest the repo exactly as the gate does — no hand-built entries.

    ``roots=[]`` keeps the walk hermetic (no toolkit conventions) while
    ``repo_root`` still drives the real ``plan/`` walk, so these tests start
    from YAML on disk exactly as production does.

    Deliberately ``build_registry`` and not ``find_repo_rules``: the runner
    guards on ``isinstance(meta, rule_id_registry.RuleMetadata)`` while
    ``find_repo_rules`` yields the identically-named ``rule_binding``
    class, so feeding its output to the runner silently yields nothing.
    ``build_registry`` converts between them, and is what the gate calls.
    """
    return build_registry(roots=[], repo_root=repo)


def test_authored_int_threshold_survives_as_an_int(tmp_path):
    """``threshold: 0`` is an int in YAML and must be an int at passes().

    ``0`` is the single most common threshold in the substrate ("zero
    duplicate side effects", "zero hardcoded literals"), and the one where
    stringification is least visible: ``'0'`` is truthy, non-empty, and
    survives every check short of an actual comparison.
    """
    repo = _consumer_repo(tmp_path, metric="zero_bar", threshold="0", value="3")
    (meta,) = [m for m in _registry(repo).values() if m.signal_metric]

    assert meta.signal_threshold == 0
    assert isinstance(meta.signal_threshold, int)
    assert not isinstance(meta.signal_threshold, str)


def test_authored_float_threshold_survives_as_a_float(tmp_path):
    """The rate-shaped case: an error budget of 0.02 must stay a float.

    This is the shape inference slices are judged by — a rate against a bar.
    ``str(0.02)`` is where a wrong-extraction budget silently stops meaning
    anything.
    """
    repo = _consumer_repo(
        tmp_path, metric="wrong_extraction_rate", threshold="0.02", value="0.074"
    )
    (meta,) = [m for m in _registry(repo).values() if m.signal_metric]

    assert meta.signal_threshold == pytest.approx(0.02)
    assert isinstance(meta.signal_threshold, float)


def test_a_violating_metric_is_caught_end_to_end_from_yaml(tmp_path):
    """7.4% measured against a 2% bar is a violation, starting from YAML.

    The regression test for #1925 proper: had this existed, the defect could
    not have shipped. It reported PASS.
    """
    repo = _consumer_repo(
        tmp_path, metric="wrong_extraction_rate", threshold="0.02", value="0.074"
    )
    violations = collect_metric_violations(_registry(repo), repo)

    assert len(violations) == 1
    assert "wrong_extraction_rate" in violations[0].detail
    assert "0.074" in violations[0].detail
    assert "0.02" in violations[0].detail


def test_a_satisfied_metric_stays_green_from_yaml(tmp_path):
    """The companion: a metric inside its budget must NOT fire.

    Without this, a fail-closed change could pass the test above by simply
    reporting everything as a violation.
    """
    repo = _consumer_repo(
        tmp_path, metric="wrong_extraction_rate", threshold="0.02", value="0.011"
    )
    assert collect_metric_violations(_registry(repo), repo) == []


def test_zero_threshold_is_enforced_not_read_as_absent(tmp_path):
    """``threshold: 0`` must be a bar, not an absence.

    A truthiness check anywhere on this path turns the strictest possible
    threshold into no threshold at all.
    """
    repo = _consumer_repo(
        tmp_path, metric="duplicate_side_effects", threshold="0", value="2"
    )
    violations = collect_metric_violations(_registry(repo), repo)

    assert len(violations) == 1
    assert "threshold=0" in violations[0].detail


def test_a_passes_that_raises_fails_closed(tmp_path):
    """An unevaluatable threshold is not a satisfied threshold.

    Treating this as a skip is what let #1925 hide: every comparison in the
    repo was raising, and the gate reported clean.
    """
    repo = _consumer_repo(
        tmp_path,
        metric="explodes",
        threshold="0",
        value="1",
        passes_body='raise ValueError("cannot judge this")',
    )
    violations = collect_metric_violations(_registry(repo), repo)

    assert len(violations) == 1
    detail = violations[0].detail
    assert "could not be evaluated" in detail
    assert "ValueError" in detail


def test_a_metric_only_acceptance_needs_no_harness(tmp_path):
    """Spec §4.3's OR is real: measurable by metric+threshold alone.

    The fixture WMBT carries no ``harness`` block anywhere. If the measurability
    OR were harness-only in practice, this acceptance would not be enforceable
    at all — and before #1925 it could not even be authored.
    """
    repo = _consumer_repo(tmp_path, metric="zero_bar", threshold="0", value="1")
    raw = (repo / "plan" / "inference_slice" / "M001.yaml").read_text(encoding="utf-8")
    assert "harness" not in raw

    from atdd.tester.validators._acceptance_walker import (
        has_harness_type,
        has_signal_metric_and_threshold,
    )
    import yaml

    block = yaml.safe_load(raw)["acceptances"][0]
    assert not has_harness_type(block)
    assert has_signal_metric_and_threshold(block)

    # ...and it is enforceable, not merely well-formed.
    assert len(collect_metric_violations(_registry(repo), repo)) == 1
