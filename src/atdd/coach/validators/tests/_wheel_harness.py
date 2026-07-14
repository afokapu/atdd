# URN: component:govern-lifecycle:enforcement-substrate:wheel_harness:backend:integration
# Runtime: python
# Purpose: Build the wheel and install it into a clean venv, once per session, for the
#          E062/C009 packaging acceptances.

"""Shared build-and-install harness for the packaging acceptances (#1474).

The packaging acceptances assert against the artifact a consumer actually
installs, so they need a real wheel and a real clean virtualenv. Both are
expensive, so both are built once per pytest session and cached here.

``--no-isolation`` keeps the build hermetic and fast (~6s vs ~40s): it reuses
the ambient ``setuptools``/``wheel`` instead of provisioning a fresh build env
from the network. The in-tree ``atdd_version_backend`` (#1172) resolves the
version from the State Store either way.
"""

from __future__ import annotations

import functools
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Set

# Held for the life of the process so the built wheel and the installed venv
# outlive the individual test that first asked for them.
_SESSION_TMP = tempfile.TemporaryDirectory(prefix="atdd-wheel-acceptance-")

# Never copied into the build tree. `build/` is the one that matters: setuptools
# does NOT clean `build/lib` between runs and `bdist_wheel` packs it wholesale, so
# a file copied there by an EARLIER build survives into every later wheel. That
# silently defeated the deny-list during development — stale `.pyc` kept appearing
# in wheels whose config excluded them perfectly. Building from a pristine copy
# means the artifact under test reflects the CURRENT config and nothing else.
#
# `__pycache__` is deliberately NOT excluded here: the source tree's byte-code is
# exactly the cruft the deny-list must filter, so copying it in is what keeps
# test_e062_smoke_001_wheel_carries_no_build_cruft honest.
_NOT_COPIED = shutil.ignore_patterns(".git", "build", "dist", "*.egg-info", "node_modules")


def repo_root() -> Path:
    """The toolkit checkout this test file lives in."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "atdd").is_dir():
            return parent
    raise RuntimeError("toolkit source tree not reachable from the test file")


@functools.lru_cache(maxsize=1)
def built_wheel() -> Path:
    """Build the wheel once, from a pristine copy of the repo, and return its path."""
    build_tree = Path(_SESSION_TMP.name) / "src-copy"
    shutil.copytree(repo_root(), build_tree, ignore=_NOT_COPIED, symlinks=True)

    outdir = Path(_SESSION_TMP.name) / "dist"
    proc = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation",
         "--outdir", str(outdir), str(build_tree)],
        # `cwd` is the pristine copy, NOT the repo root — and that is load-bearing.
        # `python -m build` resolves `build` on sys.path, which begins with the cwd. A
        # `python -m build` run by hand in the checkout leaves a (gitignored) `build/`
        # DIRECTORY there, and Python then imports THAT as a namespace package instead
        # of the real module. The acceptances start failing on a machine where the
        # packaging is perfectly fine, and the error names neither `build/` nor the
        # shadowing. The copy is built by `_NOT_COPIED`, which excludes `build`, so
        # there is nothing here to shadow it.
        cwd=str(build_tree),
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        # NOT `check=True`: that raises CalledProcessError with the real error sealed
        # inside `.stderr`, which pytest's traceback does not print. The gate then
        # reports "the build failed" and nothing else, which is indistinguishable from
        # a genuine packaging break — and sends you hunting the wrong bug.
        #
        # `build` is a `dev` extra, not a runtime dependency (see pyproject), so the
        # overwhelmingly likely cause is that it simply is not installed in the
        # interpreter running pytest. Say so, and surface the real output.
        raise RuntimeError(
            f"`{sys.executable} -m build` failed (exit {proc.returncode}) while building "
            f"the wheel these packaging acceptances assert against.\n\n"
            f"Most likely: `build` is not installed in this interpreter. It is a test-time\n"
            f"dependency of the toolkit's own validator suite:\n"
            f"    pip install 'atdd[dev]'      # or: pip install build\n"
            f"    pipx inject atdd build setuptools wheel   # if atdd is a pipx install\n\n"
            f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}"
        )
    wheels = sorted(outdir.glob("atdd-*.whl"))
    if len(wheels) != 1:
        raise RuntimeError(f"expected exactly one built wheel, got {wheels}")
    return wheels[0]


@functools.lru_cache(maxsize=1)
def wheel_members() -> Set[str]:
    """Every member path inside the built wheel, `dist-info` excluded."""
    with zipfile.ZipFile(built_wheel()) as zf:
        return {
            name for name in zf.namelist()
            if not name.endswith("/") and ".dist-info/" not in name
        }


@functools.lru_cache(maxsize=1)
def extracted_wheel_root() -> Path:
    """Unpack the wheel and return the directory holding the ``atdd/`` package.

    Importing from here reproduces exactly what a consumer's ``site-packages``
    holds — no source tree on the path, so a data file that did not ship is
    genuinely absent rather than shadowed by the checkout.
    """
    dest = Path(_SESSION_TMP.name) / "unpacked"
    if not dest.exists():
        with zipfile.ZipFile(built_wheel()) as zf:
            zf.extractall(dest)
    return dest
