# URN: test:integration-hardening:run-upgrade-unattended:E008-UNIT-005-a-dead-holder-does-not-wedge-the-install
# Acceptance: acc:integration-hardening:E008-UNIT-005-a-dead-holder-does-not-wedge-the-install
# WMBT: wmbt:integration-hardening:E008
# Phase: RED
# Layer: integration
# Runtime: python
# Assertion: behavioral
"""E008-UNIT-005 — a lock left by a dead process must not wedge the install.

RED Test for acc:integration-hardening:E008-UNIT-005-a-dead-holder-does-not-wedge-the-install
wagon: integration-hardening | feature: run-upgrade-unattended | phase: RED
WMBT: wmbt:integration-hardening:E008
Purpose: The lock must not recreate the failure it closes. An agent killed
mid-upgrade leaving sixty workers stuck behind a lock nobody holds — cleared
only by an operator — is exactly the shape of #1628 itself.

TESTER NOTE (#1628): this is driven through the public acquire/release surface
rather than by fabricating an on-disk lock file, deliberately. The acceptance
says "a process that no longer exists", which tempts a test that knows the
lock's file format and pid field; that would freeze an implementation detail
the plan never chose. Killing a real subprocess holder tests the property
without prescribing the mechanism.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap
import time

import pytest

from ._upgrade_unattended_helpers import require_symbol, subprocess_env

pytestmark = [pytest.mark.platform]


_HOLDER = textwrap.dedent(
    """
    import sys, time
    from atdd.coach.commands.upgrader import upgrade_lock
    with upgrade_lock(timeout=30):
        print("HELD", flush=True)
        time.sleep(300)
    """
)


@pytest.mark.platform
def test_e008_unit_005_killed_holder_releases_the_install(tmp_path):
    upgrade_lock = require_symbol("upgrade_lock")

    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=subprocess_env(),
    )
    try:
        line = proc.stdout.readline()
        assert line.strip() == "HELD", f"holder subprocess never took the lock: {line!r}"
        proc.kill()
        proc.wait(timeout=10)
    finally:
        if proc.poll() is None:
            proc.kill()

    # The holder is gone. A fresh acquire must succeed inside the bounded wait,
    # with no manual clean-up by anybody.
    started = time.monotonic()
    with upgrade_lock(timeout=10):
        pass
    elapsed = time.monotonic() - started

    assert elapsed < 10, (
        f"acquisition after a dead holder took {elapsed:.1f}s — the abandoned "
        "lock wedged the install"
    )


@pytest.mark.platform
def test_e008_unit_005_a_live_holder_is_still_respected(tmp_path):
    upgrade_lock = require_symbol("upgrade_lock")
    unavailable = require_symbol("UpgradeLockUnavailable")

    proc = subprocess.Popen(
        [sys.executable, "-c", _HOLDER],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        env=subprocess_env(),
    )
    try:
        line = proc.stdout.readline()
        assert line.strip() == "HELD", f"holder subprocess never took the lock: {line!r}"

        with pytest.raises(unavailable):
            with upgrade_lock(timeout=0.5):
                pass
    finally:
        proc.kill()
        proc.wait(timeout=10)
