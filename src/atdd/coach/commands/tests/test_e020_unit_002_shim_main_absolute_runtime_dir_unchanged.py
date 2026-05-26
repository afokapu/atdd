# URN: test:spawn-agents:E020-UNIT-002-shim-main-absolute-runtime-dir-unchanged
# Acceptance: acc:spawn-agents:E020-UNIT-002-shim-main-absolute-runtime-dir-unchanged
# WMBT: wmbt:spawn-agents:E020
# Phase: GREEN
# Assertion: behavioral
"""E020-UNIT-002 — when --runtime-dir is already absolute, main() passes it unchanged
to PersonaShim (resolve() is idempotent on absolute paths).

RED: fails until main() applies .resolve() and the idempotent behaviour is documented
with an explicit assertion on the received Path object.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_shim_main_absolute_runtime_dir_passed_unchanged():
    from atdd.coach.shim.__main__ import main

    captured: list[Path] = []

    class _CapturingShim:
        def __init__(self, agent_id, spawn_command, runtime_dir, env_overrides=None):
            captured.append(runtime_dir)

        def run(self):
            return 0

    with patch("atdd.coach.shim.persona_shim.PersonaShim", _CapturingShim):
        main(["--agent-id", "shim-860-abs", "--runtime-dir", "/tmp/abs-runtime-e020", "--", "echo", "ok"])

    assert captured, "E020-UNIT-002: PersonaShim was never instantiated"
    received = captured[0]

    assert isinstance(received, Path), (
        f"E020-UNIT-002: runtime_dir must be a Path. Got: {type(received)!r}"
    )
    assert received.is_absolute(), (
        f"E020-UNIT-002: absolute input must remain absolute after resolve(). Got: {received!r}"
    )
    # The path string must contain the expected segment — resolve() on an absolute
    # path is a no-op modulo symlink expansion (e.g. /tmp → /private/tmp on macOS).
    assert "abs-runtime-e020" in str(received), (
        f"E020-UNIT-002: path identity must be preserved. Got: {received!r}"
    )


def test_shim_main_absolute_runtime_dir_is_absolute():
    from atdd.coach.shim.__main__ import main

    captured: list[Path] = []

    class _CapturingShim:
        def __init__(self, agent_id, spawn_command, runtime_dir, env_overrides=None):
            captured.append(runtime_dir)

        def run(self):
            return 0

    with patch("atdd.coach.shim.persona_shim.PersonaShim", _CapturingShim):
        main(["--agent-id", "shim-860-abs2", "--runtime-dir", "/abs/path/runtime", "--", "echo", "ok"])

    assert captured
    received = captured[0]
    assert received.is_absolute(), (
        f"E020-UNIT-002: resolve() on absolute is idempotent — must still be absolute. "
        f"Got: {received!r}"
    )
