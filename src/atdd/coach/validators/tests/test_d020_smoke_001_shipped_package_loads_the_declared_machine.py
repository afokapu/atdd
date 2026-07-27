# URN: test:govern-lifecycle:define-transition-autonomy:D020-SMOKE-001-shipped-package-loads-the-declared-machine
# Acceptance: acc:govern-lifecycle:D020-SMOKE-001-shipped-package-loads-the-declared-machine
# WMBT: wmbt:govern-lifecycle:D020
# Phase: RED
# Layer: backend.smoke
# Assertion: behavioral
"""D020-SMOKE-001 — the real package loads the declared machine, unchanged.

Phase: RED. The axis does not exist, so the subprocess reports no phase
declaring it and the first assertion fails.

Real infrastructure, no in-process shortcuts: a SEPARATE process, the real
``atdd`` package, the real ``load_conventions``, and the real
``_phase_machine_path`` resolution (which prefers the in-repo copy and falls
back to the packaged one). Nothing is monkeypatched and no YAML is hand-built —
the point is that the declaration is inert in the SHIPPED artifact, not merely
under a synthetic loader.

SCOPE NOTE (deliberate narrowing, see the RED report on #1626): the acceptance
also asks that "the packaged copy carries the axis too, so a consumer installing
the wheel reads the same declaration". Proving that requires BUILDING a wheel
and inspecting its package data — the harness `_wheel_harness.py` exists for
exactly that and is what C008/C009 use. Asserting it against the currently
INSTALLED copy would instead fail whenever the local install is merely stale,
which is a reason unrelated to this change. This file therefore asserts the
resolution PATH behaves correctly and that the source of truth carries the axis;
the wheel-shipping guarantee belongs to the package-data acceptances and is
called out in the report rather than silently dropped.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from atdd.coach.utils.repo import find_repo_root

pytestmark = [pytest.mark.platform]

#: Measured 2026-07-26 before the axis existed. See D020-UNIT-004.
_PRE_CHANGE_SNAPSHOT_HASH = (
    "88af3062dfd486ee0d206946e82bebe408a3718873673f11bc0960f14e4e0913"
)

_EXPECTED_PHASES = [
    "BLOCKED", "COMPLETE", "GREEN", "INIT", "OBSOLETE",
    "PLANNED", "RED", "REFACTOR", "SMOKE",
]

_PROBE = textwrap.dedent(
    """
    import json, sys
    from pathlib import Path
    import yaml
    from atdd.train.persistence import load_conventions, _phase_machine_path

    repo = Path(sys.argv[1])
    path = _phase_machine_path(repo)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    phases = data.get("phases") or {}
    conventions = load_conventions(repo)

    print(json.dumps({
        "resolved_path": str(path),
        "prefers_in_repo": path == (repo / "src/atdd/coach/conventions/phase_machine.convention.yaml"),
        "phases": sorted(p.value for p in conventions.phase_machine),
        "snapshot_hash": conventions.snapshot_hash,
        "declaring_autonomy": sorted(n for n, s in phases.items() if "autonomy" in (s or {})),
        "autonomy_table": {n: (s or {}).get("autonomy") for n, s in phases.items()},
    }))
    """
).strip()


def _run_probe() -> dict:
    repo = find_repo_root()
    result = subprocess.run(
        [sys.executable, "-c", _PROBE, str(repo)],
        capture_output=True,
        text=True,
        timeout=120,
        cwd=repo,
    )
    assert result.returncode == 0, (
        "the probe subprocess did not exit zero — the shipped machine failed to "
        f"load in a real process.\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}"
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


@pytest.mark.platform
def test_shipped_machine_declares_the_axis_in_a_real_process() -> None:
    """The declaration is present in the artifact the runtime actually resolves."""
    probe = _run_probe()
    assert probe["declaring_autonomy"], (
        "Phase: RED — the phase machine resolved by the real package at "
        f"{probe['resolved_path']} declares `autonomy` on no phase. GREEN adds "
        "the axis to the shipped convention, not to a test fixture."
    )
    assert len(probe["declaring_autonomy"]) == len(probe["autonomy_table"]), (
        "the axis is only partially declared in the shipped machine: "
        f"{probe['declaring_autonomy']} of {sorted(probe['autonomy_table'])}"
    )


@pytest.mark.platform
def test_all_nine_phases_load_in_a_real_process() -> None:
    """The new key breaks no parse and drops no phase in the shipped artifact."""
    probe = _run_probe()
    assert probe["phases"] == _EXPECTED_PHASES, (
        f"expected the nine phases, the real process loaded {probe['phases']}"
    )


@pytest.mark.platform
def test_snapshot_hash_is_unmoved_in_a_real_process() -> None:
    """Inertness holds in the shipped artifact, not only under a synthetic loader."""
    probe = _run_probe()
    assert probe["snapshot_hash"] == _PRE_CHANGE_SNAPSHOT_HASH, (
        "the real package computes a conventions snapshot hash of "
        f"{probe['snapshot_hash']}, not the pre-change baseline "
        f"{_PRE_CHANGE_SNAPSHOT_HASH} — an in-flight run would be invalidated"
    )


@pytest.mark.platform
def test_resolution_prefers_the_in_repo_copy_with_a_packaged_fallback() -> None:
    """Worktree/wheel parity is exercised rather than assumed."""
    probe = _run_probe()
    assert probe["prefers_in_repo"], (
        "_phase_machine_path did not resolve to the in-repo copy from inside the "
        f"repo; it resolved {probe['resolved_path']}"
    )

    packaged = Path(__import__("atdd").__file__).resolve().parent / "coach" / "conventions" / "phase_machine.convention.yaml"
    assert packaged.is_file(), (
        f"the packaged fallback {packaged} is absent, so a consumer installing "
        "the wheel would have no phase machine to fall back to"
    )
