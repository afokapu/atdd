# NOT a test module (no `test_` prefix) — shared parity plumbing for the
# `resolution` family variant suites (#1212 variant wiring).
"""Helpers to execute a resolution variant through its template on the REAL
composed graph and to differentially measure legacy parity.

Imports no persona validator module, so variant suites stay runnable in parallel
with the legacy validators they measure against.
"""
from __future__ import annotations

import contextlib
from pathlib import Path
from typing import List

from .._support.graph_loader import load_composed_graph
from .archetype import TEMPLATES


def repo_root() -> Path:
    """Locate the repo root (the dir carrying both plan/ and src/atdd)."""
    here = Path(__file__).resolve()
    for anc in (here, *here.parents):
        if (anc / "plan").is_dir() and (anc / "src" / "atdd").is_dir():
            return anc
    raise RuntimeError("could not locate repo root from %s" % here)  # atdd:suppress(coach.code-roots.resolver-degrades-not-raises) — #1499 ratchet: pre-existing raising resolver; destination is zero


def evaluate_variant(template_id: str, variant: str, root=None, graph=None) -> List[dict]:
    """Execute `template_id` for `variant` against the real composed graph.

    ``graph`` lets a read-only caller pass the session-scoped clean graph (#1414);
    callers that have mutated the tree must omit it so the graph is re-read.
    """
    root = Path(root) if root else repo_root()
    g = graph if graph is not None else load_composed_graph(root)
    template = next(t for t in TEMPLATES if t.template_id == template_id)
    return template.evaluate(g, config={"variant": variant})


@contextlib.contextmanager
def inject_patch(root, rel: str, old: str, new: str):
    """Temporarily replace the first `old` with `new` in repo file `rel`."""
    path = Path(root) / rel
    original = path.read_text(encoding="utf-8")
    if old not in original:
        raise AssertionError(f"injection anchor {old!r} absent from {rel}")
    path.write_text(original.replace(old, new, 1), encoding="utf-8")
    try:
        yield
    finally:
        path.write_text(original, encoding="utf-8")
