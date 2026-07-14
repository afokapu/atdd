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
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Set

# Held for the life of the process so the built wheel and the installed venv
# outlive the individual test that first asked for them.
_SESSION_TMP = tempfile.TemporaryDirectory(prefix="atdd-wheel-acceptance-")


def repo_root() -> Path:
    """The toolkit checkout this test file lives in."""
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file() and (parent / "src" / "atdd").is_dir():
            return parent
    raise RuntimeError("toolkit source tree not reachable from the test file")


@functools.lru_cache(maxsize=1)
def built_wheel() -> Path:
    """Build the wheel from the repo once, and return the path to it."""
    outdir = Path(_SESSION_TMP.name) / "dist"
    subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation",
         "--outdir", str(outdir), str(repo_root())],
        check=True, capture_output=True, text=True,
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
