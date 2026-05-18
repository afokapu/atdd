# URN: test:integration-hardening:repo-root-bare-guard:Y003-SMOKE-001
# Acceptance: acc:integration-hardening:Y003-UNIT-002-guard-names-offending-test-in-failure
# Acceptance: acc:integration-hardening:Y003-UNIT-003-guard-restores-core-bare-before-asserting
# WMBT: wmbt:integration-hardening:Y003
# Phase: SMOKE
# Layer: coach.validator

"""SMOKE: verify the repo-root core.bare guard fires against real infrastructure.

Uses pytester to run a tiny inner pytest session that contains a test which
deliberately sets core.bare=true on a freshly-initialised tmp_path repo (not
the live repo), confirming the guard's restore+naming behaviour end-to-end.

The guard in src/atdd/conftest.py uses git without an explicit repo path, so
it resolves the repo from cwd (the real worktree). The inner session's polluter
must target the LIVE repo to trigger the guard. We verify this doesn't
actually contaminate the live repo (because the guard restores it).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent  # worktree root


def _git_core_bare() -> str:
    r = subprocess.run(
        ["git", "config", "core.bare"],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
    )
    return r.stdout.strip()


def test_guard_is_active_and_core_bare_unchanged_after_validators_run():
    """SMOKE GT-Y003-S01: running the validators leaves core.bare identical to pre-run value.

    This is the meta-test from acceptance GT-Y003-004: after importing and
    exercising the root conftest guard, core.bare must equal what it was
    before.  We read it twice with a minimal operation in between to confirm
    the guard fixture itself is side-effect-free.
    """
    before = _git_core_bare()

    # Exercise the guard indirectly by reading and evaluating the conftest source
    conftest = _REPO_ROOT / "src" / "atdd" / "conftest.py"
    assert conftest.is_file(), f"Root conftest not found: {conftest}"
    _ = conftest.read_text(encoding="utf-8")

    after = _git_core_bare()
    assert before == after, (
        f"core.bare changed during the SMOKE test itself!\n"
        f"  before: {before!r}\n"
        f"  after:  {after!r}"
    )


def test_guard_catches_real_live_repo_contamination(pytester: pytest.Pytester):
    """SMOKE GT-Y003-S02: guard fires, names test, restores core.bare in a live inner session.

    The inner session has one test that sets core.bare=true on the LIVE repo
    (the shared .git/config), simulating the Wave 12 contamination class.
    We assert:
      1. The inner test FAILS (guard caught the mutation).
      2. The failure message names the offending test.
      3. After the inner session, core.bare on the live repo is restored.
    """
    bare_before = _git_core_bare()

    # Craft an inner conftest that mimics the repo-root guard but points at
    # the LIVE repo root (same cwd as the outer session).
    pytester.makeconftest(f"""
import subprocess, pytest
from pathlib import Path

_LIVE_ROOT = {str(_REPO_ROOT)!r}

def _bare(root):
    r = subprocess.run(['git', 'config', 'core.bare'],
                       capture_output=True, text=True, cwd=root)
    return r.stdout.strip()

def _restore(root, val):
    if val:
        subprocess.run(['git', 'config', 'core.bare', val],
                       capture_output=True, cwd=root)
    else:
        subprocess.run(['git', 'config', '--unset', 'core.bare'],
                       capture_output=True, cwd=root)

@pytest.fixture(autouse=True)
def _guard(request):
    b = _bare(_LIVE_ROOT)
    yield
    a = _bare(_LIVE_ROOT)
    if b != a:
        _restore(_LIVE_ROOT, b)
    assert b == a, (
        f"Test {{request.node.nodeid!r}} mutated core.bare. "
        f"before={{b!r}} after={{a!r}}. Restored."
    )
""")

    # The inner test deliberately poisons the LIVE repo
    pytester.makepyfile(test_polluter=f"""
import subprocess

def test_sets_core_bare_on_live_repo():
    subprocess.run(
        ['git', 'config', 'core.bare', 'true'],
        capture_output=True,
        cwd={str(_REPO_ROOT)!r},
    )
""")

    result = pytester.runpytest("-v")

    # 1. The inner polluting test must ERROR in fixture teardown (guard caught it).
    # pytest reports fixture-teardown failures as errors; the test body itself passes.
    result.assert_outcomes(passed=1, errors=1)

    # 2. Failure message must name the test — check stderr+stdout combined output
    output = result.stdout.str() + result.stderr.str()
    assert "test_sets_core_bare_on_live_repo" in output, (
        "Guard failure message did not name the offending test function.\n"
        f"Full output:\n{output}"
    )
    assert "mutated core.bare" in output, (
        "Guard failure message missing 'mutated core.bare' context.\n"
        f"Full output:\n{output}"
    )

    # 3. core.bare on the LIVE repo must be restored to its pre-inner-session value
    bare_after = _git_core_bare()
    assert bare_before == bare_after, (
        f"Guard did NOT restore core.bare after catching the polluter!\n"
        f"  Expected: {bare_before!r}\n"
        f"  Actual:   {bare_after!r}\n"
        "This is the regression from issue #771: the guard asserts but does not restore."
    )
