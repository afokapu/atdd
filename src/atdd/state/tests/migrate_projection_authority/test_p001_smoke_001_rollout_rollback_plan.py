# URN: test:migrate-projection-authority:plan-migration-rollout:P001-SMOKE-001-rollout-rollback-plan
# Acceptance: acc:migrate-projection-authority:P001-SMOKE-001-rollout-rollback-plan
# WMBT: wmbt:migrate-projection-authority:P001
# Phase: SMOKE
# Layer: integration
# Runtime: python
# Assertion: behavioral
# Purpose: End-to-end — the real `atdd state rollout-check` command, run in a real checkout against the real authored .atdd/policy/migration-rollout.yaml, exits 0; and against a plan whose one-way door has lost its restore procedure, it exits non-zero and names the step. Refs #1434.
"""SMOKE — the shipped command checks the real rollout plan (P001-SMOKE-001).

wagon: migrate-projection-authority | feature: plan-migration-rollout | phase: SMOKE
WMBT: wmbt:migrate-projection-authority:P001

The plan is only worth something if the check on it is wired into a command someone actually runs.
This drives the real ``atdd state rollout-check`` in a real checkout against the real authored
plan — and then breaks the plan in the way it will really be broken (a one-way door whose restore
procedure someone left as a TODO) and proves the shipped command catches it.
Refs #1434 / #1400.
"""
from __future__ import annotations

import yaml

from ._live import REPO_ROOT, atdd_state


def test_p001_smoke_001_rollout_rollback_plan(tmp_path) -> None:
    """The real command passes on the real plan, and bites when a one-way door loses its restore."""
    repo = tmp_path / "repo"
    (repo / ".atdd" / "policy").mkdir(parents=True)
    (repo / ".atdd" / "config.yaml").write_text("version: '1.0'\n", encoding="utf-8")
    source = REPO_ROOT / ".atdd" / "policy" / "migration-rollout.yaml"
    target = repo / ".atdd" / "policy" / "migration-rollout.yaml"
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")

    passing = atdd_state(repo, "rollout-check")
    assert passing.returncode == 0, passing.stdout + passing.stderr
    assert "shadow mode before every blocking step" in passing.stdout
    assert "rollback trigger and a restore procedure" in passing.stdout

    # Break it the way it will really break: someone leaves the restore procedure empty.
    document = yaml.safe_load(target.read_text(encoding="utf-8"))
    for step in document["steps"]:
        if step["id"] == "remove-github-hot-path":
            step["rollback"]["restore"] = ""
    target.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    failing = atdd_state(repo, "rollout-check")
    assert failing.returncode != 0, failing.stdout
    report = failing.stdout + failing.stderr
    assert "remove-github-hot-path" in report, report
    assert "restore" in report
