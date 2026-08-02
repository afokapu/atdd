"""Graph-aware orchestration substrate for the coach (issue #656).

The coach's own orchestration decisions — wave planning and merge-cascade
ordering — historically used only per-issue dependency labels. This module
exposes the wagon consume graph (the same URN graph ``atdd repo graph``
walks) so the coach orchestrates with the real dependency structure:

  * ``wagon_deps`` / ``wagon_deps_transitive`` — read ``consume[].from`` edges
    from ``plan/<wagon>/_<wagon>.yaml``.
  * ``issue_wagon_map`` — read issue → wagon assignments from
    ``.atdd/manifest.yaml``.
  * ``graph_issue_deps`` — derive per-issue dependency edges from the wagon
    graph so a downstream-wagon issue is held in a later wave than its
    upstream.

All readers degrade gracefully: a missing manifest or wagon file yields an
empty result rather than raising, so planning never breaks on a partial repo.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import yaml


def _repo_root(repo_root: Optional[Path]) -> Path:
    return Path(repo_root) if repo_root is not None else Path.cwd()


def _wagon_slug(wagon: str) -> str:
    """Normalise a wagon name or ``wagon:`` URN to a bare slug."""
    return wagon.split(":", 1)[-1] if wagon.startswith("wagon:") else wagon


def _wagon_manifest_path(wagon: str, repo_root: Optional[Path]) -> Path:
    slug = _wagon_slug(wagon).replace("-", "_")
    return _repo_root(repo_root) / "plan" / slug / f"_{slug}.yaml"


def wagon_deps(wagon: str, repo_root: Optional[Path] = None) -> list[str]:
    """Return the bare wagon slugs that ``wagon`` consumes from.

    Reads ``plan/<wagon>/_<wagon>.yaml::consume[].from``. A wagon with no
    consume edges — or whose manifest is absent — returns ``[]``.
    """
    path = _wagon_manifest_path(wagon, repo_root)
    if not path.is_file():
        return []
    data = yaml.safe_load(path.read_text()) or {}
    deps: list[str] = []
    for entry in data.get("consume") or []:
        if not isinstance(entry, dict):
            continue
        src = entry.get("from")
        if not src:
            continue
        slug = _wagon_slug(str(src))
        if slug and slug not in deps:
            deps.append(slug)
    return deps


def wagon_deps_transitive(
    wagon: str, repo_root: Optional[Path] = None
) -> set[str]:
    """Return every wagon ``wagon`` consumes from, directly or transitively."""
    seen: set[str] = set()
    stack = list(wagon_deps(wagon, repo_root))
    while stack:
        current = stack.pop()
        if current in seen:
            continue
        seen.add(current)
        stack.extend(wagon_deps(current, repo_root))
    return seen


def _store_issue_wagon_map(root: Path) -> dict[int, str]:
    """Issue number → wagon map from the State Store, or {} on any miss."""
    try:
        from atdd.state.work_item_reader import WorkItemReader

        with WorkItemReader(control_root=root) as reader:
            return reader.issue_wagon_map()
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
        return {}


def issue_wagon_map(repo_root: Optional[Path] = None) -> dict[int, str]:
    """Map issue number → wagon slug, from the State Store only.

    #1270 slice D: the store is the sole read source (authoritative since #1203).
    The former ``.atdd/manifest.yaml`` fallback is retired — a cold store
    self-seeds from the manifest on first read (``WorkItemReader`` auto-import),
    so the fallback was redundant, not load-bearing.
    """
    root = _repo_root(repo_root)
    store_map = _store_issue_wagon_map(root)
    return {number: _wagon_slug(str(wagon)) for number, wagon in store_map.items()}


def graph_issue_deps(
    issue_numbers: list[int], repo_root: Optional[Path] = None
) -> dict[int, set[int]]:
    """Derive per-issue dependency edges from the wagon consume graph.

    For each issue, the returned set holds every sibling issue whose wagon the
    issue's own wagon consumes from (transitively) — so a downstream-wagon
    issue is ordered into a later wave than its upstream sibling, even when
    no explicit per-issue dependency label exists.
    """
    wmap = issue_wagon_map(repo_root)
    deps: dict[int, set[int]] = {num: set() for num in issue_numbers}
    for num in issue_numbers:
        wagon = wmap.get(num)
        if not wagon:
            continue
        upstream = wagon_deps_transitive(wagon, repo_root)
        if not upstream:
            continue
        for other in issue_numbers:
            if other != num and wmap.get(other) in upstream:
                deps[num].add(other)
    return deps
