# URN: test:bind-substrate-runtime:substrate-binding:E001-UNIT-001-spawn-captures-violations
# Acceptance: acc:bind-substrate-runtime:E001-UNIT-001-spawn-captures-violations
# WMBT: wmbt:bind-substrate-runtime:E001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""E001-UNIT-001 — a bound implementation is executed via provider-spawn
(subprocess) and its Violations are captured over the violation-output contract;
the provider/implementation module is never imported into the core process."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from atdd.substrate.binding import binder

# A fake provider adapter exposing the run contract (run_implementation -> object
# with .ran/.exit_code/.violations). It records the running process pid so the
# test can prove execution happened in a CHILD, not in core.
_FAKE_RUN_PY = """\
import os
from pathlib import Path

class _R:
    ran = True
    exit_code = 1
    violations = [
        {"rule_id": "demo.gate", "location": ".", "evidence": "first"},
        {"rule_id": "demo.gate", "location": "x.py:1", "evidence": "second"},
    ]

def run_implementation(implementation_id, test_path, *, env=None):
    Path(os.environ["BIND_PID_FILE"]).write_text(str(os.getpid()))
    return _R()
"""


def test_spawn_captures_violations_in_subprocess(tmp_path: Path) -> None:
    adapter_dir = tmp_path / "adapter"
    adapter_dir.mkdir()
    (adapter_dir / "run.py").write_text(_FAKE_RUN_PY, encoding="utf-8")
    pid_file = tmp_path / "child.pid"

    result = binder.provider_spawn(
        adapter_dir=adapter_dir,
        implementation_id="demo.gate.impl",
        test_path=tmp_path / "tests",
        env={**os.environ, "BIND_PID_FILE": str(pid_file)},
    )

    # The two emitted violations are captured and parsed.
    assert result.ran is True
    assert len(result.violations) == 2
    assert result.violations[0]["rule_id"] == "demo.gate"

    # The implementation ran in a real subprocess (its pid differs from core's).
    child_pid = int(pid_file.read_text())
    assert child_pid != os.getpid()

    # Core never imported the provider adapter module.
    assert "run" not in sys.modules or getattr(sys.modules.get("run"), "__file__", "") != str(
        adapter_dir / "run.py"
    )
