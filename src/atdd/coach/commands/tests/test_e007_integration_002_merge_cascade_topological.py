# URN: test:integration-hardening:coach-graph-aware-orchestration:E007-INTEGRATION-002-merge-cascade-topological
# Acceptance: acc:integration-hardening:E007-INTEGRATION-002-merge-cascade-topological
# WMBT: wmbt:integration-hardening:E007
# Phase: RED
# Layer: integration
# Runtime: python
"""E007-INTEGRATION-002 — the J4 merge cascade orders merges by wagon topology.

An upstream-wagon PR must merge before any PR from a wagon that consumes from
it, regardless of the order the PRs were handed to the cascade and regardless
of their PR numbers.

Intended API (the contract this RED test pins):
    merge_cascade_topology.wagon_extra_deps(pr_to_wagon: dict[int, str])
        -> dict[int, set[int]]
  Resolves the wagon consume graph and returns ``extra_deps`` edges suitable
  for ``compute_merge_order``: ``extra_deps[downstream_pr] = {upstream_pr}``.

The test deliberately uses a PR-number ordering that *contradicts* wagon
topology — downstream PR #7001 has a LOWER number than upstream PR #7002 — so
the default ascending tie-break would merge the downstream PR first. Only a
genuinely graph-aware cascade produces the correct order.

RED expectation: ``wagon_extra_deps`` does not exist yet → ImportError.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _scaffold_wagons(tmp_path: Path) -> None:
    """plan/wagon_a (upstream) and plan/wagon_b (downstream, consumes a)."""
    plan = tmp_path / "plan"
    (plan / "wagon_a").mkdir(parents=True)
    (plan / "wagon_a" / "_wagon_a.yaml").write_text(
        textwrap.dedent("""\
            wagon: wagon-a
            urn: "wagon:wagon-a"
            name: "Upstream Wagon"
            description: "Produces a contract consumed downstream."
            theme: commons
            features: []
            produce:
              - name: commons:test:upstream-contract
                to: external
            consume: []
        """)
    )
    (plan / "wagon_b").mkdir(parents=True)
    (plan / "wagon_b" / "_wagon_b.yaml").write_text(
        textwrap.dedent("""\
            wagon: wagon-b
            urn: "wagon:wagon-b"
            name: "Downstream Wagon"
            description: "Consumes the upstream contract."
            theme: commons
            features: []
            produce: []
            consume:
              - name: commons:test:upstream-contract
                from: wagon:wagon-a
        """)
    )


def test_upstream_wagon_pr_merges_before_downstream(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scaffold_wagons(tmp_path)
    monkeypatch.chdir(tmp_path)

    from atdd.coach.commands.merge_cascade_topology import (
        compute_merge_order,
        wagon_extra_deps,
    )

    # PR #7002 is the UPSTREAM wagon-a PR; PR #7001 is the DOWNSTREAM wagon-b
    # PR. Note #7001 < #7002 — the default ascending tie-break would merge the
    # downstream PR first, so this ordering is wrong unless the cascade is
    # genuinely wagon-graph-aware.
    pr_to_wagon = {7001: "wagon-b", 7002: "wagon-a"}
    extra = wagon_extra_deps(pr_to_wagon)

    # downstream PR depends on upstream PR
    assert extra.get(7001) == {7002}, f"expected {{7001: {{7002}}}}, got {extra}"

    order = compute_merge_order(
        [7001, 7002],
        fetch_diff=lambda _pr: set(),  # no file-overlap signal
        extra_deps=extra,
    )
    assert order.index(7002) < order.index(7001), (
        f"upstream wagon-a PR #7002 must merge before downstream "
        f"wagon-b PR #7001, got order {order}"
    )


def test_merge_order_is_independent_of_input_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _scaffold_wagons(tmp_path)
    monkeypatch.chdir(tmp_path)

    from atdd.coach.commands.merge_cascade_topology import (
        compute_merge_order,
        wagon_extra_deps,
    )

    pr_to_wagon = {7001: "wagon-b", 7002: "wagon-a"}
    extra = wagon_extra_deps(pr_to_wagon)

    forward = compute_merge_order([7001, 7002], lambda _p: set(), extra_deps=extra)
    reverse = compute_merge_order([7002, 7001], lambda _p: set(), extra_deps=extra)

    assert forward == reverse == [7002, 7001], (
        f"merge order must be topology-driven, not input-driven: "
        f"forward={forward} reverse={reverse}"
    )
