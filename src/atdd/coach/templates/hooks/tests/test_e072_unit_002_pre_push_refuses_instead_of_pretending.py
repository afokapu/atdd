# URN: test:govern-lifecycle:close-substrate-friction-regressions:E072-UNIT-002-pre-push-refuses-instead-of-pretending
# Acceptance: acc:govern-lifecycle:E072-UNIT-002-pre-push-refuses-instead-of-pretending
# WMBT: wmbt:govern-lifecycle:E072
# Phase: GREEN
# Layer: backend.unit
"""E072-UNIT-002 — pre-push reports registry drift truthfully (#1888).

The shipped gate exited 0 on drift after printing that it had healed. Three
verdicts have to stay distinct here, and the old code collapsed all of them into
"continuing push...": in sync, drifted, and could-not-be-checked.
"""
from __future__ import annotations

import pytest

from ._e072_registry_harness import MIRRORS, extract_block, make_repo, run_block

pytestmark = [pytest.mark.coach]

HEADING = "# --- Registry mirror drift gate"


@pytest.fixture()
def gate() -> str:
    return extract_block("pre-push", HEADING)


def test_in_sync_passes_quietly(tmp_path, gate) -> None:
    repo, env = make_repo(tmp_path)
    result = run_block(gate, repo, env)
    assert result.returncode == 0
    assert "registry" not in result.stderr.lower(), f"unexpected chatter: {result.stderr!r}"


def test_drift_refuses_the_push(tmp_path, gate) -> None:
    repo, env = make_repo(tmp_path)
    (repo / ".drift").touch()

    result = run_block(gate, repo, env)

    assert result.returncode != 0, "drift must refuse; the shipped gate exited 0"
    assert "blocked" in result.stderr.lower()


def test_the_refusal_names_the_mirrors_and_the_remedy(tmp_path, gate) -> None:
    """A refusal that names no reason is the defect class this repo keeps hitting."""
    repo, env = make_repo(tmp_path)
    (repo / ".drift").touch()

    err = run_block(gate, repo, env).stderr

    for mirror in MIRRORS:
        assert mirror in err, f"the refusal does not say {mirror} is the problem"
    assert "atdd registry update --yes" in err
    assert "git commit" in err, "the operator is not told to COMMIT the resync"


def test_an_unrunnable_check_refuses_rather_than_passing(tmp_path, gate) -> None:
    """COULD_NOT_CHECK is not PASS. With atdd absent, whether the mirrors match is
    unknown, and unknown must not be waved through."""
    repo, env = make_repo(tmp_path)
    env["PATH"] = "/usr/bin:/bin"

    result = run_block(gate, repo, env)

    assert result.returncode != 0
    assert "could not be run" in result.stderr
    assert "UNKNOWN" in result.stderr


def test_the_gate_never_claims_to_have_healed(tmp_path, gate) -> None:
    """THE REGRESSION GUARD. The shipped notice was the whole bug: it announced a
    resync that could not reach the push."""
    repo, env = make_repo(tmp_path)
    (repo / ".drift").touch()

    err = run_block(gate, repo, env).stderr

    assert "auto-resynced" not in err
    assert "continuing push" not in err


def test_the_gate_stages_nothing(tmp_path, gate) -> None:
    repo, env = make_repo(tmp_path)
    (repo / ".drift").touch()

    run_block(gate, repo, env)

    staged = run_block("git diff --cached --name-only", repo, env).stdout.strip()
    assert staged == "", f"pre-push staged {staged!r}, which can never reach the push"
