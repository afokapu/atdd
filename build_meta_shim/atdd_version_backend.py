"""In-tree PEP 517 build backend: project version from the ATDD State Store (#1172).

This wraps :mod:`setuptools.build_meta` unchanged and supplies the project
``version`` for ``dynamic = ["version"]`` via the :data:`VERSION` attribute,
which is resolved from the State Store SQLite by the stdlib-only
:mod:`_release_version` resolver alongside this module.

It runs under build isolation (``pip``/``build`` create an env with only
``setuptools`` installed), so it MUST NOT import ``atdd`` — version resolution is
stdlib only and re-implements a minimal Control-Root resolver. Resolution is
**local-first** with an explicit ``0.0.0+local`` no-store fallback so a fresh
clone / pre-``atdd state init`` build never fails.

``pyproject.toml`` wires this via::

    [build-system]
    build-backend = "atdd_version_backend"
    backend-path = ["build_meta_shim"]

    [project]
    dynamic = ["version"]

    [tool.setuptools.dynamic]
    version = {attr = "atdd_version_backend.VERSION"}
"""
from __future__ import annotations

# Re-export every PEP 517 hook from setuptools so this module IS a complete build
# backend (build_wheel / build_sdist / build_editable / prepare_metadata_* /
# get_requires_for_build_*). We add nothing to them — the version is supplied
# statically via the `attr` pointer to VERSION below.
from setuptools.build_meta import *  # noqa: F401,F403 — re-export build hooks

# `backend-path = ["build_meta_shim"]` puts this directory on sys.path during the
# build, so the sibling stdlib-only resolver imports by bare module name.
from _release_version import LOCAL_FALLBACK_VERSION, resolve_version  # noqa: F401

#: Resolved once at backend import — setuptools reads this via the `attr` pointer.
VERSION = resolve_version()
