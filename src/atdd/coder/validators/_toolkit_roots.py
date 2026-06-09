# URN: component:govern-lifecycle:config-driven-four-tier-validators:toolkit_roots:backend:application
# Runtime: python
# Purpose: Resolve four-tier validator scan roots from .atdd/config.yaml, reconciling discovery vs import root (#958).

"""Config-driven scan-root resolution for the four-tier coder validators (#958).

The composition-completeness and wagon-boundaries validators historically pinned
the consumer ``python/`` directory as BOTH the discovery root (where wagon/feature
trees live) and the import-resolution base (where a dotted import resolves on
disk). For the toolkit's own code these two roots DIFFER:

* discovery root  = ``src/atdd``  — wagons live one level under it
  (``src/atdd/<wagon>/<feature>/src/<layer>/...``)
* import root     = ``src``       — the ``atdd`` package resolves from here, so
  toolkit code imports cross-package as ``atdd.<wagon>.<feature>.src.<layer>...``

Conflating them is exactly what produced the ~25 false "unwired" violations when
#955 pointed composition at ``src/atdd`` (every ``atdd.`` import failed to resolve
against a ``python`` base, so every layer looked unconsumed). ``ScanRoot`` carries
both roots plus the package ``import_prefix`` so attribution can strip it.

This module is a pure application-layer unit: it reads the existing
``.atdd/config.yaml`` ``code:`` block via :func:`get_code_roots` and returns the
roots to scan. The two validators are thinned to call it.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Mapping, Optional

from atdd.coach.utils.config import get_code_roots

# Negative composition/boundary fixtures live here and are intentionally broken;
# they must never be discovered when the toolkit root is scanned, or they would
# self-trigger the very violations they exist to test.
FIXTURES_MARKER = "coder/validators/fixtures"


@dataclass(frozen=True)
class ScanRoot:
    """A root the four-tier validators scan, with discovery/import reconciled.

    Attributes:
        discovery_root: directory whose immediate children are wagons (e.g.
            ``<repo>/src/atdd`` or ``<repo>/python``).
        import_root: directory a dotted import resolves against on disk (e.g.
            ``<repo>/src`` for the toolkit, ``<repo>/python`` for the consumer).
        import_prefix: the package segment(s) that ``discovery_root`` adds on top
            of ``import_root`` (``"atdd"`` for the toolkit, ``""`` for the
            consumer where the wagon itself is the top-level import segment).
    """

    discovery_root: Path
    import_root: Path
    import_prefix: str

    def strip_import_prefix(self, dotted: str) -> str:
        """Drop the package ``import_prefix`` from a dotted import path.

        ``atdd.mediate_worker_decisions.x`` -> ``mediate_worker_decisions.x`` for
        a toolkit root; a no-op when ``import_prefix`` is empty.
        """
        prefix = self.import_prefix.strip(".")
        if not prefix:
            return dotted
        head = prefix + "."
        return dotted[len(head):] if dotted.startswith(head) else dotted


def is_excluded_fixture(path: Path) -> bool:
    """True when *path* sits under the negative-fixtures tree."""
    return FIXTURES_MARKER in path.as_posix()


def _abs(root: Path, repo_root: Path) -> Path:
    return root if root.is_absolute() else (repo_root / root)


def resolve_scan_roots(
    config: Optional[Mapping[str, Any]], repo_root: Path
) -> List[ScanRoot]:
    """Resolve the four-tier scan roots declared in ``.atdd/config.yaml``.

    The consumer ``python`` stack is always returned (discovery == import root,
    no package prefix). The ``toolkit`` stack is returned ONLY when
    ``code.toolkit`` is explicitly declared (:func:`get_code_roots` never seeds it
    by default — Decision #1 of #327), with its import root reconciled to the
    parent directory and the package name as ``import_prefix``.

    Non-existent roots are still returned; the finders guard on ``.exists()`` so a
    repo that ships only one of the two trees simply yields no files for the
    other.
    """
    code_roots = get_code_roots(config)
    roots: List[ScanRoot] = []

    python_rel = code_roots.get("python")
    if python_rel is not None:
        discovery = _abs(python_rel, repo_root)
        roots.append(
            ScanRoot(discovery_root=discovery, import_root=discovery, import_prefix="")
        )

    toolkit_rel = code_roots.get("toolkit")
    if toolkit_rel is not None:
        discovery = _abs(toolkit_rel, repo_root)
        # The toolkit dir name IS the top-level package (``src/atdd`` -> ``atdd``
        # resolving from ``src``); the import root is therefore its parent.
        roots.append(
            ScanRoot(
                discovery_root=discovery,
                import_root=discovery.parent,
                import_prefix=discovery.name,
            )
        )

    return roots
