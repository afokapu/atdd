# URN: test:govern-lifecycle:upgrade-banner:E068-SMOKE-001-live-upgrade-banner-names-a-runnable-verb
# Acceptance: acc:govern-lifecycle:E068-SMOKE-001-live-upgrade-banner-names-a-runnable-verb
# WMBT: wmbt:govern-lifecycle:E068
# Phase: SMOKE
# Layer: smoke
# Assertion: behavioral
# Runtime: python
"""E068-SMOKE-001 — the real banner names a verb an agent can actually run.

    Read from the shipped `version_check.py`, not a synthetic string.

The unit sibling patches `check_upgrade_sync_needed` and asserts on the value it
was handed, so it keeps passing whatever the real banner says. #1811 changed the
verb and only a source-reading check notices.

The banner has to name something runnable. `atdd init` returns 1 on an
already-initialised repo (#1600) and `atdd init --force` is forbidden (#793), so
a banner naming either teaches an agent to run a command that cannot succeed —
which is how `--force` kept being suggested. With the agent-config projection
retired there is no `atdd sync` step either; `atdd upgrade` is the verb that acts.
"""
from __future__ import annotations

import re

import pytest

from atdd.coach.utils.config import resolve_code_root
from atdd.coach.utils.repo import find_repo_root

pytestmark = pytest.mark.platform

REPO_ROOT = find_repo_root()
_TOOLKIT = resolve_code_root("toolkit", REPO_ROOT)

#: Lines that build the operator-facing upgrade banner.
_BANNER = re.compile(r'^\s*(?:msg\s*=|return)\s*f?"ATDD upgraded[^"]*"', re.M)


def _banner_lines() -> list[str]:
    if _TOOLKIT is None:
        pytest.skip("no code.toolkit declared — not the toolkit's own checkout")
    src = (_TOOLKIT / "version_check.py").read_text(encoding="utf-8")
    found = _BANNER.findall(src) or [m.group(0) for m in _BANNER.finditer(src)]
    if not found:
        pytest.fail("no upgrade banner found in version_check.py — the regex has drifted")
    return found


def test_every_banner_names_a_runnable_verb() -> None:
    for line in _banner_lines():
        assert "atdd upgrade" in line, f"banner names no runnable verb: {line.strip()}"


def test_no_banner_advertises_the_forbidden_flag() -> None:
    for line in _banner_lines():
        assert "--force" not in line, f"banner advertises a forbidden flag: {line.strip()}"


def test_no_banner_names_the_retired_two_step() -> None:
    """`atdd sync && atdd init` could not act on an initialised repo (#1600)."""
    for line in _banner_lines():
        assert "atdd sync && atdd init" not in line, line.strip()
