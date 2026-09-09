# URN: component:code:enforce:InterlockingLayoutScope:backend:src
# Runtime: python
# Purpose: decide which rules receive the per-repo interlocking scan surfaces (#1867).
"""Which rules receive the per-repo interlocking layout.

Split out of ``conventions.py``: that module reasons about declared convention
data, while this one probes the vendored substrate on disk. Keeping the I/O here
also keeps ``conventions.py`` inside the file-length budget.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from atdd.enforce.conventions import _INTERLOCKING_LAYOUT_SELECTOR_IDS

__all__ = ["package_declares_interlocking_surfaces"]


def package_declares_interlocking_surfaces(substrate_home: Path, package_id: str) -> bool:
    """True iff the vendored ``package_id`` declares the layout's selector surfaces.

    The layout exists so a repo whose runtime does not sit at the detector's default
    globs can say where it does. The question "does this rule consume that?" is
    answered by the package that DECLARES the surfaces, not by how the rule happens
    to be named — a name prefix is the same bug waiting for the next rule name, and
    it already bit once (#1867).

    Scope selector ids are namespaced with the surface as the LAST segment
    (``coder.train.python_runtime`` -> ``python_runtime``), which the extension's own
    scope file documents as a contract. Matching on that segment keeps core out of
    the extension's namespacing choices.

    Returns False on any unreadable or absent scope — an undeclared package simply
    does not get the env var, which is the pre-existing fallback, not a new failure.
    """
    # ``substrate_home`` is the REPO ROOT; the vendored trees live under its
    # ``.atdd/``, exactly as ``_resolve_impls_root`` walks them. Dropping that
    # segment silently returns False for every package, which starves every rule
    # rather than feeding the seven this fix exists for — caught by the ratchet,
    # not by the unit tests, because those hand-passed the already-joined path.
    pkg_root = Path(substrate_home) / ".atdd" / "extensions" / package_id
    if not pkg_root.is_dir():
        return False
    wanted = set(_INTERLOCKING_LAYOUT_SELECTOR_IDS)
    for scope_path in sorted(pkg_root.glob("*/scopes/*.yaml")):
        try:
            doc = yaml.safe_load(scope_path.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            continue
        for selector in doc.get("selectors") or []:
            if not isinstance(selector, dict):
                continue
            sid = selector.get("selector_id")
            if isinstance(sid, str) and sid.rsplit(".", 1)[-1] in wanted:
                return True
    return False
