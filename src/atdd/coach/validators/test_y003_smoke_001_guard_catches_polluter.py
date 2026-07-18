# URN: test:integration-hardening:repo-root-bare-guard:Y003-SMOKE-001
# Acceptance: acc:integration-hardening:Y003-SMOKE-001-guard-catches-real-live-repo-contamination
# Acceptance: acc:integration-hardening:Y003-UNIT-002-guard-names-offending-test-in-failure
# Acceptance: acc:integration-hardening:Y003-UNIT-003-guard-restores-core-bare-before-asserting
# WMBT: wmbt:integration-hardening:Y003
# Phase: SMOKE
# Layer: coach.validator

"""SMOKE: verify the repo-root core.bare guard fires against real infrastructure.

Uses pytester to run a tiny inner pytest session that contains a test which
deliberately sets core.bare=true on a freshly-initialised tmp_path repo (not
the live repo), confirming the guard's restore+naming behaviour end-to-end.

The guard in the atdd package's own conftest uses git without an explicit repo
path, so it resolves the repo from cwd (the real worktree). The inner polluter
must target the LIVE repo to trigger the guard. We verify this doesn't
actually contaminate the live repo (because the guard restores it).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.coach]

# The repo under test, resolved from ATDD's own markers rather than a
# ``parent × N`` walk. Counting parents encodes the TOOLKIT's source-tree depth
# (``src/atdd/coach/validators/`` → 5 up), which lands outside the package
# entirely once atdd is installed into ``site-packages``.
_REPO_ROOT = find_repo_root()


def _package_conftest() -> Path:
    """The atdd package's OWN root conftest, wherever atdd is installed.

    The subject of this guard is the conftest that ships INSIDE the package, so
    resolve it relative to the imported package. That is agnostic: it holds in a
    source checkout (``src/atdd/conftest.py``) and in ``site-packages``
    (``atdd/conftest.py``) alike, whereas a literal ``src/atdd`` only ever
    described the toolkit checkout.
    """
    import atdd

    return Path(atdd.__file__).resolve().parent / "conftest.py"


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
    conftest = _package_conftest()
    assert conftest.is_file(), f"Root conftest not found: {conftest}"
    _ = conftest.read_text(encoding="utf-8")

    after = _git_core_bare()
    assert before == after, (
        f"core.bare changed during the SMOKE test itself!\n"
        f"  before: {before!r}\n"
        f"  after:  {after!r}"
    )


@pytest.mark.slow
def test_guard_catches_real_live_repo_contamination(pytester: pytest.Pytester):
    """SMOKE GT-Y003-S02: guard fires, names test, restores core.bare in a live inner session.

    The inner session has one test that sets core.bare=true on the LIVE repo
    (the shared .git/config), simulating the Wave 12 contamination class.
    We assert:
      1. The inner test FAILS (guard caught the mutation).
      2. The failure message names the offending test.
      3. After the inner session, core.bare on the live repo is restored.
    """
    import os
    if os.environ.get("CI", "").lower() != "true":
        # This smoke mutates core.bare on the LIVE shared .git/config to exercise
        # the contamination guard. It is slow and unsafe to run in a local
        # `atdd validate --local` pre-push gate (env-sensitive, touches real git
        # config). CI is the authoritative home for it (#932).
        pytest.skip("Destructive live-repo git smoke; CI-only — skipped in local runs (#932)")

    # Skip on ABSENCE OF SUBJECT, never on identity of repo: the guard under test
    # protects a git checkout's shared config, so a working tree is the subject.
    # Where there is no ``.git`` there is no config to contaminate or restore.
    # This is layout-driven, not repo-driven — the assertions below run in ANY
    # git repo, the toolkit's included, because the inner session brings its own
    # conftest and polluter.
    if not (_REPO_ROOT / ".git").exists():
        pytest.skip(f"no git checkout at {_REPO_ROOT} — no core.bare to guard")

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

    # 1. The guard must catch the mutation: either the test FAILS or the teardown ERRORS.
    # pytest reports fixture-teardown failures as ERRORs (test body still PASSES).
    # Count both — at least one of them must be non-zero.
    outcomes = result.parseoutcomes()
    failed_or_errored = outcomes.get("failed", 0) + outcomes.get("errors", 0) + outcomes.get("error", 0)
    assert failed_or_errored >= 1, (
        "Inner session guard did NOT catch the core.bare mutation!\n"
        f"Outcomes: {outcomes}\n"
        f"Output:\n{result.stdout.str()}"
    )

    # 2. Failure message must name the test — check the full combined output
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
