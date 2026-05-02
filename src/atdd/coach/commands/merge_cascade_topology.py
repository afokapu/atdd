"""
Topological-sort engine for `atdd merge-cascade`.

Builds a DAG over PR numbers from file-overlap signals and returns a
deterministic merge order. Cycles raise ``MergeCascadeCycleError`` with
the offending path.

SPEC IDs: SPEC-COACH-ORCH-0008 (DAG topology), SPEC-COACH-ORCH-0009 (cycle
detection).

Design:
- Edge signal: shared file in PR diffs (Decision #1, issue #365).
- Edge orientation: lower PR → higher PR (acyclic by construction).
- Tie-break: ascending PR number (Decision #2).
- ``extra_deps`` injection lets callers add explicit edges (e.g. for
  fixture-driven cycle tests or future explicit dependency declarations).

Pure helper — no I/O. Diff-fetching and dependency-source resolution
happen in callers.
"""
from __future__ import annotations

from typing import Callable, Optional


class MergeCascadeCycleError(RuntimeError):
    """Raised when the dependency graph contains a cycle.

    The ``cycle_path`` attribute is a list of PR numbers forming the cycle,
    closing on itself (e.g. ``[1, 2, 3, 1]``). The message lists every PR
    in the cycle for actionable error reporting.
    """

    def __init__(self, cycle_path: list[int]):
        self.cycle_path = cycle_path
        path_str = " → ".join(f"#{n}" for n in cycle_path)
        super().__init__(f"merge-cascade detected a cycle: {path_str}")


def _build_graph(
    pr_numbers: list[int],
    fetch_diff: Callable[[int], set[str]],
    extra_deps: Optional[dict[int, set[int]]] = None,
) -> dict[int, set[int]]:
    """Return adjacency where ``graph[pr]`` is the set of PRs that must merge first."""
    files = {pr: set(fetch_diff(pr) or set()) for pr in pr_numbers}
    graph: dict[int, set[int]] = {pr: set() for pr in pr_numbers}

    sorted_prs = sorted(pr_numbers)
    for i, lower in enumerate(sorted_prs):
        for higher in sorted_prs[i + 1:]:
            if files[lower] & files[higher]:
                graph[higher].add(lower)

    if extra_deps:
        for pr, deps in extra_deps.items():
            if pr in graph:
                graph[pr].update(d for d in deps if d in graph)

    return graph


def _find_cycle(graph: dict[int, set[int]]) -> list[int]:
    """Return a closed cycle path (e.g. ``[1, 2, 3, 1]``) or ``[]`` if acyclic."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in graph}
    parent: dict[int, int] = {}

    def dfs(start: int) -> Optional[list[int]]:
        stack: list[tuple[int, list[int]]] = [(start, sorted(graph[start]))]
        color[start] = GRAY
        while stack:
            node, remaining = stack[-1]
            if not remaining:
                color[node] = BLACK
                stack.pop()
                continue
            nxt = remaining.pop(0)
            if color.get(nxt, BLACK) == GRAY:
                cycle = [nxt]
                cur = node
                while cur != nxt:
                    cycle.append(cur)
                    cur = parent[cur]
                cycle.append(nxt)
                cycle.reverse()
                return cycle
            if color.get(nxt) == WHITE:
                parent[nxt] = node
                color[nxt] = GRAY
                stack.append((nxt, sorted(graph[nxt])))
        return None

    for node in sorted(graph):
        if color[node] == WHITE:
            cycle = dfs(node)
            if cycle:
                return cycle
    return []


def _kahn(graph: dict[int, set[int]]) -> list[int]:
    """Kahn's topological sort with ascending-PR tie-break.

    Assumes ``graph`` is acyclic — caller must verify with ``_find_cycle``.
    """
    indeg = {n: len(deps) for n, deps in graph.items()}
    successors: dict[int, list[int]] = {n: [] for n in graph}
    for n, deps in graph.items():
        for d in deps:
            successors[d].append(n)

    ready = sorted(n for n, d in indeg.items() if d == 0)
    order: list[int] = []
    while ready:
        n = ready.pop(0)
        order.append(n)
        for s in successors[n]:
            indeg[s] -= 1
            if indeg[s] == 0:
                ready.append(s)
        ready.sort()
    return order


def compute_merge_order(
    pr_numbers: list[int],
    fetch_diff: Callable[[int], set[str]],
    extra_deps: Optional[dict[int, set[int]]] = None,
) -> list[int]:
    """Topologically sort PRs by file-overlap dependencies.

    Args:
        pr_numbers: PRs to order.
        fetch_diff: callable returning the set of files changed by a PR.
        extra_deps: optional explicit edges. ``extra_deps[pr]`` is the set
            of PRs that must merge before ``pr``.

    Returns:
        Deterministic merge order (ascending PR number on ties).

    Raises:
        MergeCascadeCycleError: if the combined graph contains a cycle.
    """
    if not pr_numbers:
        return []

    graph = _build_graph(pr_numbers, fetch_diff, extra_deps=extra_deps)
    cycle = _find_cycle(graph)
    if cycle:
        raise MergeCascadeCycleError(cycle)
    return _kahn(graph)
