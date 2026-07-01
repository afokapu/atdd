# URN: test:state-store:version-projection:live-build-metadata
# Issue: #1281 (Version SoT Store Projection Implementation; umbrella #1172)
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""#1281 LIVE smoke — the full store->build->``importlib.metadata`` version path.

This is the load-bearing live smoke the design (`docs/version-source-of-truth-design.md`
S1-S4) requires and that #1269 left as an explicit gap: it does a **real** build +
install of the ``atdd`` package and asserts that the version recorded in the
installed distribution's metadata is exactly the value bumped in the State Store.

Run for real, no mock / no skip (E027 /
``tester.acceptance-violation.live-smoke-acceptance-must-execute``):

    real Control Root + State Store
      -> ``state/version.py`` bump (release object -> a distinctive version)
      -> the in-tree PEP 517 backend (``build_meta_shim/atdd_version_backend.py``)
         resolves that version from the store at build time (``ATDD_CONTROL_ROOT``)
      -> a REAL ``pip wheel`` build of this repo
      -> a REAL ``pip install`` of that wheel into an isolated venv
      -> ``importlib.metadata.version("atdd")`` in that venv == the bumped version.

The final ``importlib.metadata.version`` assertion is the point: build/runtime
version resolves from the store-derived projection, not a hand-edited
``pyproject`` line (which is ``dynamic`` now) and not the ``0.0.0+local`` no-store
fallback.
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from atdd.state.db import connect, init_state_store
from atdd.state import version as ver
from atdd.state.migrations import RELEASE_SEED_VERSION

# repo root: .../src/atdd/state/tests/this_file.py -> parents[4]
_REPO_ROOT = Path(__file__).resolve().parents[4]
_BUILD_TIMEOUT_S = 600
_INSTALL_TIMEOUT_S = 600


def _venv_python(venv_dir: Path) -> Path:
    bindir = "Scripts" if os.name == "nt" else "bin"
    return venv_dir / bindir / ("python.exe" if os.name == "nt" else "python")


def _run(cmd, *, env=None, timeout):
    return subprocess.run(
        cmd, cwd=str(_REPO_ROOT), env=env, capture_output=True, text=True, timeout=timeout,
    )


def test_installed_metadata_version_matches_store_bump(tmp_path):
    # 1. Real on-disk Control Root + State Store, seeded at RELEASE_SEED_VERSION.
    root = tmp_path / "control-root"
    root.mkdir()
    db = init_state_store(db_path=root / ".atdd" / "state" / "state.sqlite")

    # 2. Bump to a distinctive value clearly distinct from both the seed and the
    #    no-store fallback, so a build that ignored the store (fell back, or read a
    #    stale value) cannot coincidentally pass. MAJOR + MINOR + PATCH -> 4.1.1.
    conn = connect(db)
    try:
        ver.bump(conn, "MAJOR", pr="1281")   # 3.149.0 -> 4.0.0
        ver.bump(conn, "MINOR", pr="1281")   # 4.0.0   -> 4.1.0
        expected = ver.bump(conn, "PATCH", pr="1281")   # 4.1.0 -> 4.1.1
        assert expected == ver.current(conn)
    finally:
        conn.close()
    assert expected != RELEASE_SEED_VERSION
    assert expected != ver.LOCAL_FALLBACK_VERSION

    # 3. REAL wheel build. Build isolation runs the in-tree backend, which resolves
    #    the version from the store pointed to by ATDD_CONTROL_ROOT.
    build_env = dict(os.environ)
    build_env["ATDD_CONTROL_ROOT"] = str(root)
    wheelhouse = tmp_path / "wheelhouse"
    wheelhouse.mkdir()
    built = _run(
        [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(wheelhouse), "."],
        env=build_env, timeout=_BUILD_TIMEOUT_S,
    )
    assert built.returncode == 0, f"wheel build failed:\nSTDOUT:\n{built.stdout}\nSTDERR:\n{built.stderr}"

    wheels = list(wheelhouse.glob("atdd-*.whl"))
    assert len(wheels) == 1, f"expected exactly one atdd wheel, got {wheels}"
    wheel = wheels[0]
    # pip encodes the resolved (store-derived) version into the wheel filename.
    assert f"atdd-{expected}-" in wheel.name, (
        f"wheel {wheel.name!r} does not carry the store-bumped version {expected!r}"
    )

    # 4. REAL install into an isolated venv (metadata only; --no-deps keeps it fast
    #    and offline-of-PyPI for deps — the version lives in the wheel METADATA).
    venv_dir = tmp_path / "venv"
    made = _run([sys.executable, "-m", "venv", str(venv_dir)], timeout=_INSTALL_TIMEOUT_S)
    assert made.returncode == 0, f"venv create failed:\n{made.stderr}"
    vpy = _venv_python(venv_dir)
    installed = _run(
        [str(vpy), "-m", "pip", "install", "--no-deps", str(wheel)],
        timeout=_INSTALL_TIMEOUT_S,
    )
    assert installed.returncode == 0, f"wheel install failed:\n{installed.stderr}"

    # 5. LOAD-BEARING: importlib.metadata in the installed env returns the bump.
    got = _run(
        [str(vpy), "-c",
         "import importlib.metadata as m; import sys; sys.stdout.write(m.version('atdd'))"],
        timeout=_INSTALL_TIMEOUT_S,
    )
    assert got.returncode == 0, f"metadata read failed:\n{got.stderr}"
    assert got.stdout.strip() == expected, (
        f"importlib.metadata.version('atdd') was {got.stdout.strip()!r}, "
        f"expected the store-bumped {expected!r}"
    )
