# URN: test:admit-substrate:substrate-admission:C001-SMOKE-001-add-does-not-execute
# Acceptance: acc:admit-substrate:C001-SMOKE-001-add-does-not-execute
# WMBT: wmbt:admit-substrate:C001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C001-SMOKE-001 — `atdd add --path <poisoned-package>` as a real subprocess
admits (or refuses on manifest grounds) without ever executing the poisoned
implementation: the sentinel is never written and the poisoned RuntimeError never
surfaces. The `add` command must genuinely exist (not an argparse 'invalid choice')."""
from __future__ import annotations

import pathlib
import subprocess
import sys

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "poisoned_extension"


def test_atdd_add_does_not_execute_poisoned_implementation(tmp_path) -> None:
    sentinel = tmp_path / "executed.sentinel"
    env = {
        "ATDD_C001_SENTINEL": str(sentinel),
        "CI": "true",
    }
    import os

    env = {**os.environ, **env}
    proc = subprocess.run(
        [sys.executable, "-m", "atdd", "add", "--path", str(FIXTURE)],
        cwd=str(tmp_path),
        capture_output=True,
        text=True,
        env=env,
    )
    combined = proc.stdout + proc.stderr
    # `add` must be a real command, not an argparse rejection (would be a false green).
    assert "invalid choice: 'add'" not in combined, "atdd add is not wired as a command"
    # The no-execution invariant: the poisoned implementation never ran.
    assert not sentinel.exists(), "poisoned implementation executed during `atdd add`"
    assert "POISONED" not in combined, "poisoned RuntimeError surfaced during `atdd add`"
