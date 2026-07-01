"""Canonical valid/invalid REAL-graph fragments for the `policy` family (#1212).

The `policy/forbidden_construct_absence` evaluator executes against the REAL
composed graph: it reads `graph.root` and the real files / WMBT acceptance nodes
that a variant scopes onto. These fixtures therefore adapt INTO the graph model —
each builder seeds a tiny slice of a real repo under a tmp root and returns a
genuine ``ConventionGraph`` (real ``Node`` objects, real ``root``). No dict
fragments are fed to the evaluator; the fixtures only differ from the full repo
in scale, not in kind.

``VALID_FRAGMENTS`` / ``INVALID_FRAGMENTS`` map each variant to the builder that
seeds its clean / faulted graph slice.
"""
from __future__ import annotations

from pathlib import Path

from .._support.graph_loader import ConventionGraph, Node


def _graph(root: Path, nodes=()) -> ConventionGraph:
    g = ConventionGraph(root=root)
    for n in nodes:
        g._add(n)
    return g


# --- smoke_synthetic_fixture_bypass ----------------------------------------
def seed_smoke_synthetic(root: Path, *, faulted: bool) -> ConventionGraph:
    """Seed a wagon dir + a resolvable SMOKE test file; faulted injects FakeMultiplexer."""
    pkg = root / "src" / "atdd" / "demo"
    pkg.mkdir(parents=True, exist_ok=True)
    body = "def test_e999_smoke_001_demo():\n    assert True\n"
    if faulted:
        body = "from x import FakeMultiplexer\n" + body
    (pkg / "test_e999_smoke_001_demo.py").write_text(body, encoding="utf-8")
    wmbt = Node(
        id="wmbt:demo:E999", kind="wmbt", location="plan/demo/E999.yaml", package="demo",
        fields={"acceptances": [
            {"identity": {"urn": "acc:demo:E999-SMOKE-001-demo", "phase": "SMOKE"}}
        ]},
    )
    return _graph(root, [wmbt])


# --- no_stale_suppressions -------------------------------------------------
def seed_stale_suppressions(root: Path, *, faulted: bool) -> ConventionGraph:
    """Seed a src/atdd file; faulted carries a suppression marker past its UNTIL date."""
    pkg = root / "src" / "atdd" / "demo"
    pkg.mkdir(parents=True, exist_ok=True)
    line = "x = 1\n"
    if faulted:
        # Assemble the pragma at runtime so this committed builder does not itself
        # carry a contiguous `atdd:suppress(...)` marker that the scanner would flag.
        pragma = "atdd:" + "suppress(demo.rule)" + " UNTIL=2000-01-01"
        line = f"x = 1  # {pragma}\n"
    (pkg / "mod.py").write_text(line, encoding="utf-8")
    return _graph(root)


# --- freedom_layer_bash_scope (E032) ---------------------------------------
def seed_freedom_layer(root: Path, *, faulted: bool) -> ConventionGraph:
    """Seed session.convention.yaml; faulted pre-authorizes a forbidden command."""
    conv_dir = root / "src" / "atdd" / "coach" / "conventions"
    conv_dir.mkdir(parents=True, exist_ok=True)
    allowed = "['Bash(pytest:*)', 'Bash(grep:*)']"
    if faulted:
        allowed = "['Bash(pytest:*)', 'Bash(git push:*)']"
    (conv_dir / "session.convention.yaml").write_text(
        "spawn_time:\n"
        "  freedom_layer:\n"
        f"    allowed_bash: {allowed}\n"
        "    forbidden_bash: ['git push', 'rm', 'sudo']\n",
        encoding="utf-8",
    )
    return _graph(root)


# --- bypass_inventory (E026) -----------------------------------------------
def seed_bypass_inventory(root: Path, *, faulted: bool) -> ConventionGraph:
    """Seed a pre-push hook; faulted reintroduces an ATDD_SKIP_* bypass flag."""
    hooks = root / "src" / "atdd" / "coach" / "templates" / "hooks"
    hooks.mkdir(parents=True, exist_ok=True)
    body = "#!/bin/sh\nexit 0\n"
    if faulted:
        body = '#!/bin/sh\nif [ "${ATDD_SKIP_DEMO:-0}" = "1" ]; then exit 0; fi\n'
    (hooks / "pre-push").write_text(body, encoding="utf-8")
    return _graph(root)


VALID_FRAGMENTS = {
    "smoke_synthetic_fixture_bypass": lambda root: seed_smoke_synthetic(root, faulted=False),
    "no_stale_suppressions": lambda root: seed_stale_suppressions(root, faulted=False),
    "freedom_layer_bash_scope": lambda root: seed_freedom_layer(root, faulted=False),
    "bypass_inventory": lambda root: seed_bypass_inventory(root, faulted=False),
}

INVALID_FRAGMENTS = {
    "smoke_synthetic_fixture_bypass": lambda root: seed_smoke_synthetic(root, faulted=True),
    "no_stale_suppressions": lambda root: seed_stale_suppressions(root, faulted=True),
    "freedom_layer_bash_scope": lambda root: seed_freedom_layer(root, faulted=True),
    "bypass_inventory": lambda root: seed_bypass_inventory(root, faulted=True),
}
