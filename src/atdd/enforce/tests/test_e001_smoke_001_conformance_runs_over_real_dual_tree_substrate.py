# URN: test:govern-providers:E001-SMOKE-001-conformance-runs-over-real-dual-tree-substrate
# Acceptance: acc:govern-providers:E001-SMOKE-001-conformance-runs-over-real-dual-tree-substrate
# WMBT: wmbt:govern-providers:E001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:govern-providers:E001-SMOKE-001-conformance-runs-over-real-dual-tree-substrate.

Over the toolkit's own real committed ``.atdd/binding.lock.yaml`` and its vendored
workspaces + extensions trees, the conformance check exercises the dual-tree
(#1359) resolution live: every bound rule's runnability is resolved by searching
BOTH ``.atdd/workspaces`` and ``.atdd/extensions``. It must return a report over
the real lock without raising.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.runner import _bound_conventions, conformance, resolve_substrate_home


def test_conformance_runs_over_real_dual_tree_substrate() -> None:
    repo_root = find_repo_root()

    ok, report = conformance(repo_root)

    assert isinstance(ok, bool)
    assert isinstance(report, str) and report.strip()

    substrate_home = resolve_substrate_home(repo_root)
    bound = _bound_conventions(substrate_home)
    # The report names the bound-rule runnability count over the real lock.
    assert f"/{len(bound)} bound rules runnable" in report
