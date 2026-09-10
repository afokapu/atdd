# URN: test:govern-lifecycle:close-substrate-friction-regressions:E023-UNIT-001-skip-all-gates-sets-all-four-flags
# Acceptance: acc:govern-lifecycle:E023-UNIT-001-skip-all-gates-sets-all-four-flags
# WMBT: wmbt:govern-lifecycle:E023
# Phase: GREEN
# Layer: backend.unit
"""AC-UNIT-001: a routine push needs no env-var bypass, and the one escape that
remains keeps a record (#1893).

E023 proposed `ATDD_SKIP_ALL_GATES` to collapse four skip-flags into one. E026
then measured that as structurally additive — "the individual flags still work
independently, the meta-bypass just lowered the typing cost of bypassing
everything" — and retired the whole class for the audited `atdd emergency`.

Both acceptances were left standing, so this test asserted a flag another
acceptance required to be absent and has been red ever since E026 shipped. E026
won in the code; E023's GOAL survives and is better served by it. What changed is
the mechanism, so this asserts the mechanism that exists.
"""
from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

REPO_ROOT = Path(__file__).resolve().parents[6]
HOOKS_DIR = REPO_ROOT / "src" / "atdd" / "coach" / "templates" / "hooks"
HOOK_FILES = ("pre-push", "pre-commit", "post-commit", "commit-msg", "pre-merge-commit")

RETIRED_FLAGS = ("ATDD_SKIP_ALL_GATES", "ATDD_SKIP_POSTCOMMIT", "ATDD_SKIP_REGISTRY_CHECK")


def _hook(name: str) -> str:
    return (HOOKS_DIR / name).read_text(encoding="utf-8")


@pytest.mark.parametrize("flag", RETIRED_FLAGS)
def test_no_env_var_bypass_survives_in_any_hook(flag: str) -> None:
    """A gate that a variable can wave through has a behavioural cost of zero."""
    present = [name for name in HOOK_FILES if flag in _hook(name)]
    assert not present, (
        f"{flag} is still honoured by: {', '.join(present)}.\n"
        "E026 retired this class; the audited `atdd emergency` is the replacement."
    )


def test_the_meta_flag_specifically_is_gone() -> None:
    """Named separately because it is the one E023 itself proposed. A single flag
    that waves through everything records nothing about what was skipped."""
    assert "ATDD_SKIP_ALL_GATES" not in _hook("pre-push")


def test_the_surviving_escape_is_the_audited_one() -> None:
    text = _hook("pre-push")
    assert "EMERGENCY_BYPASS" in text, (
        "the pre-push hook honours no escape at all; E026 retired the env-var "
        "flags in favour of `atdd emergency`, not in favour of nothing."
    )
    assert "reason" in text.lower(), "a bypass that records no reason is not audited"


def test_the_escape_is_time_bounded() -> None:
    """An expired bypass that is still honoured is a permanent bypass with a
    misleading name."""
    text = _hook("pre-push")
    assert "-mmin" in text or "expired" in text.lower(), (
        "the emergency bypass has no TTL check, so the file grants a permanent "
        "exemption once written."
    )
