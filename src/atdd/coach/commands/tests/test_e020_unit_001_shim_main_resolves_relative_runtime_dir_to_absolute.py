# URN: test:spawn-agents:E020-UNIT-001-shim-main-resolves-relative-runtime-dir-to-absolute
# Acceptance: acc:spawn-agents:E020-UNIT-001-shim-main-resolves-relative-runtime-dir-to-absolute
# WMBT: wmbt:spawn-agents:E020
# Phase: GREEN
# Assertion: behavioral
"""E020-UNIT-001 — atdd-shim main() resolves a relative --runtime-dir to absolute
before constructing PersonaShim; PersonaShim.runtime_dir is absolute.

Belt-and-suspenders guard: even if a caller bypasses the E019 fix in cmd_spawn,
the shim normalizes the path on entry.

RED: fails until main() calls args.runtime_dir.resolve() before passing it to PersonaShim.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch


def test_shim_main_resolves_relative_runtime_dir(tmp_path, monkeypatch):
    from atdd.coach.shim.__main__ import main

    captured_runtime_dir: list[Path] = []

    class _CapturingShim:
        def __init__(self, agent_id, spawn_command, runtime_dir, env_overrides=None):
            captured_runtime_dir.append(runtime_dir)

        def run(self):
            return 0

    monkeypatch.chdir(tmp_path)

    # PersonaShim is imported lazily inside main() from atdd.coach.shim.persona_shim.
    with patch("atdd.coach.shim.persona_shim.PersonaShim", _CapturingShim):
        main(["--agent-id", "shim-860-rel", "--runtime-dir", ".atdd/runtime", "--", "echo", "ok"])

    assert captured_runtime_dir, "E020-UNIT-001: PersonaShim was never instantiated"
    received = captured_runtime_dir[0]

    assert isinstance(received, Path), (
        f"E020-UNIT-001: runtime_dir passed to PersonaShim must be a Path. Got: {type(received)!r}"
    )
    assert received.is_absolute(), (
        f"E020-UNIT-001: PersonaShim must receive an absolute runtime_dir. "
        f"Got: {received!r} (relative). "
        "Fix: add args.runtime_dir = args.runtime_dir.resolve() after argparse in main()."
    )


def test_shim_main_resolved_path_ends_with_expected_suffix(tmp_path, monkeypatch):
    from atdd.coach.shim.__main__ import main

    captured: list[Path] = []

    class _CapturingShim:
        def __init__(self, agent_id, spawn_command, runtime_dir, env_overrides=None):
            captured.append(runtime_dir)

        def run(self):
            return 0

    monkeypatch.chdir(tmp_path)

    with patch("atdd.coach.shim.persona_shim.PersonaShim", _CapturingShim):
        main(["--agent-id", "shim-860-suffix", "--runtime-dir", ".atdd/runtime", "--", "echo", "ok"])

    assert captured
    received = captured[0]
    # The resolved absolute path must end with the relative suffix we passed.
    assert str(received).endswith(".atdd/runtime"), (
        f"E020-UNIT-001: resolved path must end with '.atdd/runtime'. Got: {received!r}"
    )
    assert received.is_absolute(), (
        f"E020-UNIT-001: resolved path must be absolute. Got: {received!r}"
    )
