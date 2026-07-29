# URN: test:govern-lifecycle:define-transition-autonomy:D020-SMOKE-001-shipped-package-loads-the-declared-machine
# Acceptance: acc:govern-lifecycle:D020-SMOKE-001-shipped-package-loads-the-declared-machine
# WMBT: wmbt:govern-lifecycle:D020
# Phase: SMOKE
# Layer: backend.smoke
# Assertion: behavioral
"""D020-SMOKE-001 — the real package loads the declared machine, unchanged.

Real infrastructure, no in-process shortcuts: a SEPARATE process, the real
``atdd`` package, the real ``load_conventions``, and the real
``_phase_machine_path`` resolution (which prefers the in-repo copy and falls
back to the packaged one). Nothing is monkeypatched and no YAML is hand-built —
the point is that the declaration is inert in the SHIPPED artifact, not merely
under a synthetic loader.

THE SHIPPED-ARTIFACT CLAIM (SMOKE, #1626). ``_phase_machine_path`` PREFERS the
in-repo copy, so a probe run inside the checkout reads the worktree — which is
NOT the claim this acceptance makes. The currently installed atdd (4.27.0)
predates this change and carries neither the axis nor the node, and always will
until a release ships, so asserting against it would assert "my unmerged change
has been released" — unsatisfiable at SMOKE and a reason unrelated to the
change.

The claim that IS both real and satisfiable: the artifact a consumer WILL
install carries the declaration. So the wheel-backed tests below build the wheel
from this tree via the existing `_wheel_harness` (the same harness C008/C009
use) and read the axis out of the unpacked wheel with NO source tree on the
path — where a data file that did not ship is genuinely absent rather than
shadowed by the checkout. That closes the narrowing flagged in the RED report.
"""
from __future__ import annotations

import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
import yaml

from atdd.coach.utils.repo import find_repo_root

from ._d020_autonomy import EXPECTED_PHASES, PINNED, PRE_CHANGE_SNAPSHOT_HASH

pytestmark = [pytest.mark.coach, pytest.mark.platform]


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
        "REGRESSION: the phase machine resolved by the real package at "
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
    assert probe["phases"] == EXPECTED_PHASES, (
        f"expected the nine phases, the real process loaded {probe['phases']}"
    )


@pytest.mark.platform
def test_snapshot_hash_is_unmoved_in_a_real_process() -> None:
    """Inertness holds in the shipped artifact, not only under a synthetic loader."""
    probe = _run_probe()
    assert probe["snapshot_hash"] == PRE_CHANGE_SNAPSHOT_HASH, (
        "the real package computes a conventions snapshot hash of "
        f"{probe['snapshot_hash']}, not the pre-change baseline "
        f"{PRE_CHANGE_SNAPSHOT_HASH} — an in-flight run would be invalidated"
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


# --------------------------------------------------------------------------- #
# The shipped-artifact half: assert against a real wheel, not the worktree.    #
# --------------------------------------------------------------------------- #


@pytest.mark.platform
def test_built_wheel_ships_the_axis_and_the_node() -> None:
    """Both files are package DATA, so a consumer's install actually contains them.

    Reuses the C008/C009 harness. Package data is opt-in in this project's
    packaging config, so a convention YAML that exists in the tree can silently
    fail to ship — the exact class of miss #1474/#1602 were filed for.
    """
    from ._wheel_harness import extracted_wheel_root, wheel_members

    members = wheel_members()
    for rel in (
        "atdd/coach/conventions/phase_machine.convention.yaml",
        "atdd/coach/conventions/nodes/coach.lifecycle.transition-autonomy.convention.yaml",
    ):
        assert rel in members, (
            f"{rel} is not in the built wheel, so a consumer installing atdd would "
            "not receive it — the declaration would exist only in this checkout"
        )

    shipped = yaml.safe_load(
        (extracted_wheel_root() / "atdd" / "coach" / "conventions"
         / "phase_machine.convention.yaml").read_text(encoding="utf-8")
    )["phases"]
    assert {n: (s or {}).get("autonomy") for n, s in shipped.items()} == PINNED, (
        "the wheel's phase machine does not carry the pinned autonomy table; "
        f"it carries {[(n, (s or {}).get('autonomy')) for n, s in shipped.items()]}"
    )


@pytest.mark.platform
def test_consumer_install_loads_the_axis_with_no_source_tree_on_the_path() -> None:
    """The packaged FALLBACK resolves the declared machine, not just the checkout.

    Runs the loader against the unpacked wheel with the source tree absent from
    sys.path and a repo root that holds no ``src/atdd``, so ``_phase_machine_path``
    is forced down its packaged-copy branch — the branch a consumer always takes
    and the one the in-repo probe above never exercises.
    """
    import os
    import tempfile

    from ._wheel_harness import extracted_wheel_root

    with tempfile.TemporaryDirectory(prefix="atdd-consumer-") as tmp:
        env = dict(os.environ, PYTHONPATH=str(extracted_wheel_root()))
        env.pop("PYTHONHOME", None)
        result = subprocess.run(
            [sys.executable, "-c", _PROBE, tmp],
            capture_output=True, text=True, timeout=180, cwd=tmp, env=env,
        )
        assert result.returncode == 0, (
            "the consumer-shaped probe failed to load the shipped machine.\n"
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}"
        )
        probe = json.loads(result.stdout.strip().splitlines()[-1])

    assert not probe["prefers_in_repo"], (
        "the probe still resolved an in-repo copy; the consumer fallback branch "
        f"was not exercised (resolved {probe['resolved_path']})"
    )
    assert str(extracted_wheel_root()) in probe["resolved_path"], (
        "the loader did not resolve the unpacked WHEEL's convention; it resolved "
        f"{probe['resolved_path']} — the source tree is shadowing the artifact"
    )
    assert probe["autonomy_table"] == PINNED, (
        "a consumer installing this wheel reads a different autonomy table than "
        f"the one declared: {probe['autonomy_table']}"
    )
    assert probe["phases"] == EXPECTED_PHASES
    assert probe["snapshot_hash"] == PRE_CHANGE_SNAPSHOT_HASH, (
        "the shipped artifact hashes differently from the pre-change baseline, "
        "so installing it would invalidate a consumer's in-flight run snapshot"
    )
