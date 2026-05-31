# URN: component:govern-lifecycle:enforcement-substrate:test_hook_version_gate_honest_message:backend:domain
# Runtime: python
# Purpose: The git-hook version gate must give an HONEST diagnostic on ImportError
#          (point at `atdd doctor`), not the misleading "requires a newer atdd" (#928 Gap 4).
"""
Regression test for the git-hook version-gate message (issue #928 Gap 4).

When the hook's ``python3`` cannot import atdd, the old templates printed
``"version gate requires a newer atdd package"`` and told the operator to
``pipx upgrade atdd``. That is a lie: the package is current; the real fault
is that the interpreter running the hook cannot import atdd (an
environment/path problem). The misleading message cost a full session of
reverse-engineering.

The fix: on ImportError the hooks must say so honestly and point at
``atdd doctor``. These tests pin both shipped hook templates to that
behavior so a future edit cannot silently reintroduce the lie.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import atdd

pytestmark = [pytest.mark.coach]


_HOOKS_DIR = Path(atdd.__file__).resolve().parent / "coach" / "templates" / "hooks"
_GATED_HOOKS = ("pre-push", "pre-merge-commit")


@pytest.mark.parametrize("hook_name", _GATED_HOOKS)
def test_hook_version_gate_is_honest(hook_name: str):
    hook = _HOOKS_DIR / hook_name
    assert hook.is_file(), f"missing hook template: {hook}"
    text = hook.read_text(encoding="utf-8")

    # The hook must still HAVE a version gate.
    assert "_gate_main" in text, f"{hook_name} lost its version gate"

    # It must NOT assert staleness as the cause of an ImportError.
    assert "requires a newer atdd package" not in text, (
        f"{hook_name} still prints the misleading 'requires a newer atdd "
        f"package' on ImportError; the real fault is that the hook's python3 "
        f"cannot import atdd. Say so and point at `atdd doctor`."
    )

    # It must point at the honest diagnosis command.
    assert "atdd doctor" in text, (
        f"{hook_name} must point at `atdd doctor` so the operator/agent gets "
        f"the real cause instead of reverse-engineering it."
    )
