"""Canonical valid/invalid REAL-graph fragments for the `coherence` family (#1212).

Fixtures adapt INTO the real graph model: each fragment is a small
``ConventionGraph`` of real ``Node`` objects (NOT a dict), so a fragment exercises
the exact same ``resolved_fact_agreement`` evaluator that runs on the composed repo
graph. ``theme_archetype_alignment`` is filesystem-bound (it resolves a wagon's
source root on disk), so its fragment is built by ``build_archetype_graph(root)``
against a tmp tree rather than declared as static data.
"""
from __future__ import annotations

from pathlib import Path

from .._support.graph_loader import ConventionGraph, Node


def _graph(*nodes: Node, root: Path | None = None) -> ConventionGraph:
    g = ConventionGraph(root=root)
    for n in nodes:
        g._add(n)
    return g


def _wagon(slug: str, theme: str, *, produce=None, wmbt=None, location=None) -> Node:
    fields = {"wagon": slug, "theme": theme}
    if produce is not None:
        fields["produce"] = produce
    if wmbt is not None:
        fields["wmbt"] = wmbt
    return Node(id=f"wagon:{slug}", kind="wagon",
                location=location or f"plan/{slug.replace('-', '_')}/_{slug.replace('-', '_')}.yaml",
                package=slug.replace("-", "_"), theme=theme, fields=fields)


def _wmbt_node(slug_pkg: str, code: str) -> Node:
    return Node(id=f"wmbt:{slug_pkg.replace('_', '-')}:{code}", kind="wmbt",
                location=f"plan/{slug_pkg}/{code}.yaml", package=slug_pkg, fields={})


def _train(train_id: str, family, terminal_artifact) -> Node:
    fields = {"train_id": train_id, "sequence": [{"step": 1, "artifact": terminal_artifact}]}
    if family is not None:
        fields["family"] = family
    return Node(id=f"train:{train_id}", kind="train",
                location=f"plan/_trains/{train_id}.yaml", fields=fields)


# --- theme_urn_namespace_matches -------------------------------------------
VALID_FRAGMENTS = {
    # coach wagon producing coach:* URNs — prefixes agree with the theme.
    "theme_urn_namespace_matches": _graph(
        _wagon("mediate-ok", "coach",
               produce=[{"name": "coach:decision:record"}]),
    ),
    # train family agrees with terminal contract (delivery -> commit-receipt).
    "train_family_matches_terminal_contract": _graph(
        _train("9003-x", "delivery", "platform:acceptance:commit-receipt"),
        _train("9004-x", "behavior", "identity:sign-in:session-created"),
        _train("9005-x", None, "platform:acceptance:commit-receipt"),  # no family -> not flagged
    ),
    # manifest WMBT declarations exactly match the filesystem WMBT files.
    "wmbt_consistency": _graph(
        _wagon("widget", "commons", wmbt={"total": 2, "E001": "stmt", "E002": "stmt"}),
        _wmbt_node("widget", "E001"),
        _wmbt_node("widget", "E002"),
    ),
}

INVALID_FRAGMENTS = {
    # coach wagon producing a commons:* URN — prefix disagrees with theme.
    "theme_urn_namespace_matches": _graph(
        _wagon("mediate-it", "coach",
               produce=[{"name": "commons:decision:record"}]),
    ),
    # delivery train whose terminal artifact is NOT a commit-receipt.
    "train_family_matches_terminal_contract": _graph(
        _train("9002-x", "delivery", "identity:sign-in:session-created"),
    ),
    # manifest declares a WMBT code (E999) that has no file on disk.
    "wmbt_consistency": _graph(
        _wagon("widget", "commons", wmbt={"total": 2, "E001": "stmt", "E999": "stmt"}),
        _wmbt_node("widget", "E001"),
    ),
}


def build_archetype_graph(root: Path, *, aligned: bool) -> ConventionGraph:
    """Build a filesystem-backed fragment for ``theme_archetype_alignment``.

    Creates a `code`-themed wagon whose source dir lives under the coder root
    (``aligned=True``) or under the planner root (``aligned=False`` -> violation).
    """
    slug = "impl-thing"
    pkg = slug.replace("-", "_")
    archetype = "coder" if aligned else "planner"
    src = root / "src" / "atdd" / archetype / pkg
    src.mkdir(parents=True, exist_ok=True)
    (src / "__init__.py").write_text("", encoding="utf-8")
    return _graph(_wagon(slug, "code"), root=root)
