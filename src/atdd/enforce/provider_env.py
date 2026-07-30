"""The environment a provider subprocess runs under.

Core never imports a provider — the whole contract is "run a CLI and read v1.1
JSON off stdout" — so **env is core's only lever** over how that run behaves.
Everything core wants to tell a provider therefore arrives here, and this module
is the one place that decides what a provider process sees.

Split out of :mod:`atdd.enforce.runner`, which had accumulated the scan surface,
the reachability roots, the interlocking layout and the cache suppression
alongside the invocation and parsing logic. Building the environment and running
the subprocess are separate concerns with separate reasons to change.
"""

from __future__ import annotations

import json
import os
from typing import Optional

#: Env var the train-interlocking detector reads as its HIGHEST-precedence
#: scan-surface source (contract step 1, #1595): JSON ``{selector_id: [globs]}``.
#: Core sets it ONLY for a ``coder.train.interlocking-*`` rule whose repo declares
#: an ``interlocking_layout`` block; otherwise it is never set and the detector
#: falls back to its own scope selectors / defaults. Never leaked onto unrelated
#: rule subprocesses.
INTERLOCKING_LAYOUT_ENV = "ATDD_INTERLOCKING_LAYOUT"

# The provider CLI imports vendored adapter modules and then subprocesses
# ``python -m pytest`` over a test file INSIDE the vendored tree. Both writes land
# in that tree — ``__pycache__/`` next to every imported module, ``.pytest_cache/``
# at the resolved rootdir — mutating a digest-locked substrate that core is
# supposed to leave untouched, which surfaced as a false ``[TAMPERED]`` from
# ``--verify-substrate`` (#1603). The vendored adapter's pytest argv is fixed and
# digest-locked, so env is core's only lever: it inherits down the whole chain
# (core → provider CLI → pytest), and ``PYTEST_ADDOPTS`` is how a caller adds
# pytest flags without owning the argv.
_PYTEST_NO_CACHE_OPT = "-p no:cacheprovider"


def cache_suppressing_env() -> dict[str, str]:
    """Env that keeps a provider run from depositing caches in the vendored tree."""
    addopts = os.environ.get("PYTEST_ADDOPTS", "").strip()
    return {
        "PYTHONDONTWRITEBYTECODE": "1",
        # Appended, not clobbered: an operator's own PYTEST_ADDOPTS still applies.
        "PYTEST_ADDOPTS": (
            f"{addopts} {_PYTEST_NO_CACHE_OPT}" if addopts else _PYTEST_NO_CACHE_OPT
        ),
    }


def provider_env(
    implementation_id: str,
    scan_roots: list[str],
    scan_excludes: list[str],
    graph_roots: Optional[list[str]] = None,
    interlocking_layout: Optional[dict] = None,
) -> dict[str, str]:
    """The full environment for one provider subprocess.

    Every optional input is omitted when absent rather than emitted empty: a
    detector distinguishes "core said nothing" from "core said none", and the
    fallbacks it owns (its own scope selectors, its own defaults) only engage on
    the former.

    ``graph_roots`` (the consumer's resolved CLI entry-point module files) are
    forwarded as ``ATDD_GRAPH_ROOTS`` for reachability detectors that consume
    explicit extra roots. KNOWN GAP (#1238 / docs/PARITY-AUDIT-26.md REGRESSION
    #3): the enforce layer supplies them, but the vendored python-pytest dead-code
    detector does not yet READ ``ATDD_GRAPH_ROOTS`` — that detector-side
    consumption awaits the extension re-vendor. Forwarding it now means parity
    closes the moment the fixed detector is re-vendored, with no further core
    change. (We cannot patch the vendored detector here: it is digest-locked by
    ``.atdd/substrate.lock.yaml`` and re-vendoring is the convergence step.)

    ``interlocking_layout`` (the repo's declared ``{selector_id: [globs]}`` scan
    surfaces) is forwarded as ``ATDD_INTERLOCKING_LAYOUT`` when — and only when —
    the caller supplies one, i.e. for a ``coder.train.interlocking-*`` rule in a
    repo that declares the block (#1595).
    """
    env = {
        **os.environ,
        "ATDD_SCAN_ROOTS": json.dumps([str(r) for r in scan_roots]),
        "ATDD_IMPL_ID": implementation_id,
        **cache_suppressing_env(),
    }
    if scan_excludes:
        env["ATDD_SCAN_EXCLUDES"] = json.dumps([str(e) for e in scan_excludes])
    if graph_roots:
        env["ATDD_GRAPH_ROOTS"] = json.dumps([str(r) for r in graph_roots])
    if interlocking_layout:
        env[INTERLOCKING_LAYOUT_ENV] = json.dumps(interlocking_layout)
    return env
