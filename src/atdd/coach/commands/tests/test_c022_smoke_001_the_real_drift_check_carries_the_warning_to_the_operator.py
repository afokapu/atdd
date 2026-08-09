# URN: test:govern-lifecycle:enforcing-artifact-declaration:C022-SMOKE-001-the-real-drift-check-carries-the-warning-to-the-operator
# Acceptance: acc:govern-lifecycle:C022-SMOKE-001-the-real-drift-check-carries-the-warning-to-the-operator
# WMBT: wmbt:govern-lifecycle:C022
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""
AC-SMOKE-001: the declaration warning reaches the operator through the real
check, not only through a direct call to the formatter.

Real ``RegistryBuilder``, real drift detection, real check-mode dispatch, real
``format_fix_hint`` — nothing stubbed or monkeypatched. The repository is a
``tmp_path`` fixture, so the filesystem is the only infrastructure involved:
``execution_kind: hermetic_integration``, as declared on the acceptance.

The drift is the one a WMBT-adding branch produces — a wagon manifest whose
``wmbt.total`` the mirror does not carry — which is exactly the case that caught
#1726's own worker.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from atdd.coach.commands.registry import RegistryBuilder


def _write_repo(root: Path, *, mirror_total: int) -> Path:
    """A repo whose wagon manifest declares 3 WMBTs and whose mirror declares
    ``mirror_total``. Equal totals mean no drift."""
    plan_dir = root / "plan"
    wagon_dir = plan_dir / "my_wagon"
    wagon_dir.mkdir(parents=True)

    manifest = {
        "wagon": "my-wagon",
        "description": "My wagon",
        "theme": "commons",
        "subject": "agent:coder",
        "context": "in-lifecycle",
        "action": "acts",
        "goal": "achieves",
        "outcome": "achieved",
        "wmbt": {"total": 3},
    }
    (wagon_dir / "_my_wagon.yaml").write_text(yaml.dump(manifest))

    mirror_entry = {
        **{k: v for k, v in manifest.items() if k != "wmbt"},
        "wmbt": {"total": mirror_total},
        "manifest": "plan/my_wagon/_my_wagon.yaml",
        "path": "plan/my_wagon/",
        "produce": [],
        "consume": [],
        "total": 0,
    }
    (plan_dir / "_wagons.yaml").write_text(yaml.dump({"wagons": [mirror_entry]}))
    return root


@pytest.fixture()
def drifted_repo(tmp_path: Path) -> Path:
    """Mirror still says 2 WMBTs while the source says 3 — DRIFT."""
    return _write_repo(tmp_path, mirror_total=2)


@pytest.fixture()
def synced_repo(tmp_path: Path) -> Path:
    """Mirror and source agree — the discriminating control."""
    return _write_repo(tmp_path, mirror_total=3)


def _run_check(repo: Path) -> None:
    RegistryBuilder(repo).update_wagon_registry(mode="check")


def test_the_real_check_reports_drift_and_carries_the_declaration_warning(
    drifted_repo, capsys
):
    """The consequence arrives through the surface the operator actually reads."""
    _run_check(drifted_repo)
    output = "".join(capsys.readouterr())

    assert "Drift detected" in output, f"expected the run to report drift. Got:\n{output}"
    assert "## Artifacts" in output, (
        f"the real check must carry the declaration warning. Got:\n{output}"
    )
    assert "git diff --name-only origin/main..HEAD" in output, (
        f"the real check must carry the re-derivation command. Got:\n{output}"
    )


def test_the_warning_names_the_mirror_that_is_about_to_be_appended(
    drifted_repo, capsys
):
    """The warning is about the files the amend will actually add."""
    _run_check(drifted_repo)
    output = "".join(capsys.readouterr())
    assert "_wagons.yaml" in output, (
        f"the drifted mirror must be named in the output. Got:\n{output}"
    )
    assert "git commit --amend --no-edit" in output, (
        f"the amend the warning is about must be named. Got:\n{output}"
    )


def test_a_synced_repo_gets_neither_the_warning_nor_the_amend(synced_repo, capsys):
    """The discriminating control: drift is what produces the warning, not the
    code path being unconditional."""
    _run_check(synced_repo)
    output = "".join(capsys.readouterr())

    assert "registry is in sync" in output, (
        f"expected the control repo to report no drift. Got:\n{output}"
    )
    assert "## Artifacts" not in output, (
        f"an in-sync repo must not be warned about its declaration. Got:\n{output}"
    )
    assert "--amend" not in output, (
        f"an in-sync repo must not be told to amend. Got:\n{output}"
    )
