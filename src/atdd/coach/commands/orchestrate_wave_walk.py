"""Dependency-graph walker used by ``atdd issue <N> --orchestrate``.

Two pure functions live here so they're unit-testable without mocking gh:

- :func:`_parse_dependencies` — extracts ``#NNN`` refs from the
  ``### Dependencies`` section of a parent issue body.
- :func:`_compute_wave` — walks the transitive dep graph from a starting
  issue number, using caller-supplied ``fetch`` and ``is_complete``
  callables so the network layer can be swapped out.

The CLI entry point :func:`orchestrate_from_issue` wires the pure helpers
to real GitHub fetches and hands the computed wave to ``atdd orchestrate``.
"""
from __future__ import annotations

import re
import subprocess
from typing import Callable, List, Set


_DEPENDENCIES_HEADING_RE = re.compile(r"^###\s+Dependencies\s*$", re.MULTILINE)
_HASH_REF_RE = re.compile(r"#(\d+)")


def _parse_dependencies(body: str) -> List[int]:
    """Return the ordered list of ``#NNN`` issue numbers declared in the
    ``### Dependencies`` subsection of ``body``.

    Only refs that appear *inside* the Dependencies section count — a ``#999``
    mention in another section (Context, Notes, ...) is ignored. Duplicates
    are dropped while preserving first-occurrence order.
    """
    if not body:
        return []

    match = _DEPENDENCIES_HEADING_RE.search(body)
    if match is None:
        return []

    tail = body[match.end():]
    next_heading = re.search(r"^(?:##\s|###\s)", tail, re.MULTILINE)
    section = tail[: next_heading.start()] if next_heading else tail

    seen: Set[int] = set()
    ordered: List[int] = []
    for m in _HASH_REF_RE.finditer(section):
        number = int(m.group(1))
        if number in seen:
            continue
        seen.add(number)
        ordered.append(number)
    return ordered


def _compute_wave(
    start: int,
    fetch_body: Callable[[int], str],
    is_complete: Callable[[int], bool],
) -> List[int]:
    """Walk the dep graph rooted at ``start`` and return the wave.

    The wave is the set of non-COMPLETE issues reachable from ``start`` via
    ``### Dependencies`` refs, in DFS order with cycles broken by a visited
    set. ``start`` is always included (unless it is itself COMPLETE).
    """
    wave: List[int] = []
    visited: Set[int] = set()

    def _visit(number: int) -> None:
        if number in visited:
            return
        visited.add(number)
        if is_complete(number):
            return
        wave.append(number)
        body = fetch_body(number)
        for dep in _parse_dependencies(body):
            _visit(dep)

    _visit(start)
    return wave


def _gh_fetch_body(issue_number: int) -> str:
    """Fetch an issue body via ``gh issue view``. Empty string on any error."""
    try:
        result = subprocess.run(
            ["gh", "issue", "view", str(issue_number), "--json", "body"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return ""
        import json
        return json.loads(result.stdout).get("body") or ""
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return ""


def _gh_is_complete(issue_number: int) -> bool:
    """Return True if the issue has the ``atdd:COMPLETE`` label or is closed."""
    try:
        result = subprocess.run(
            ["gh", "issue", "view", str(issue_number), "--json", "state,labels"],
            capture_output=True,
            text=True,
            timeout=15,
        )
        if result.returncode != 0:
            return False
        import json
        data = json.loads(result.stdout)
        if data.get("state") == "CLOSED":
            return True
        for label in data.get("labels", []):
            name = label.get("name", "") if isinstance(label, dict) else str(label)
            if name == "atdd:COMPLETE":
                return True
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError, ValueError):
        return False


def orchestrate_from_issue(issue_number: int) -> int:
    """CLI entry for ``atdd issue <N> --orchestrate``.

    Computes the wave starting at ``issue_number`` and delegates to
    ``atdd orchestrate <wave...>``. Returns the orchestrate process's exit
    code, or 1 on a local failure.
    """
    wave = _compute_wave(issue_number, _gh_fetch_body, _gh_is_complete)
    if not wave:
        print(f"Wave for #{issue_number} is empty (issue may already be COMPLETE).")
        return 0

    print(f"Computed wave from #{issue_number}: {wave}")
    try:
        result = subprocess.run(
            ["atdd", "orchestrate", *[str(n) for n in wave]],
            check=False,
        )
        return result.returncode
    except FileNotFoundError:
        print("Error: `atdd` binary not found on PATH.")
        return 1
