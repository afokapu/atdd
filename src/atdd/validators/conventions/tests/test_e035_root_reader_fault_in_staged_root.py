# URN: test:validate-conventions:tune-convention-suite:E035-GREEN-001-root-reader-fault-in-staged-root
# Acceptance: acc:validate-conventions:E035-RED-001-root-reader-fault-rewrites-the-checkout
# Acceptance: acc:validate-conventions:E035-GREEN-001-root-reader-fault-injected-into-staged-root
# WMBT: wmbt:validate-conventions:E035
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""E035 — the root-reading fault families inject into a staged root (#1458).

#1416 migrated the five families whose evaluators read their fault from a graph NODE.
The seven left over mostly do not: policy's hook and suppression scanners, grammar's and
schema's whole-file readers, and composition's package-data reader take the graph purely
as a carrier for ``.root`` and then read real files off disk. There is no node to mutate,
so ``clone_graph`` cannot reach them — but the graph they were rebuilding was never used
for anything except that one ``Path``.

E035-RED-001 (the retired mechanism): the fault used to be injected by rewriting a real
TRACKED file in the checkout — a git hook, ``session.convention.yaml``, ``pyproject.toml``,
a committed SMOKE test — and reverting it in a ``finally``.
``test_on_disk_fault_rewrites_the_checkout`` characterizes that hazard against the
retained policy ``_parity.overwrite_file`` oracle. Note these are NOT the YAML surfaces
E034 guards: a YAML-only residue check would not have caught any of them.

E035-GREEN-001 asserts the MECHANISM: the staged tree is byte-identical to the real file
apart from the injected fault, the evaluator flags it, a fault transform that changes
nothing raises instead of passing vacuously, and the session graph's ids AND root come
back unchanged. Build counts are reported as measured numbers on the PR, never asserted —
a wall-clock gate is cheapest to satisfy by deleting the fault coverage it exists to
protect.
"""
from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

import pytest

from atdd.validators.conventions._support.graph_mutations import (
    add_node,
    graph_rooted_at,
    mirror_file,
    node_at,
    stage_file,
)
from atdd.validators.conventions.policy import _parity as policy_parity
from atdd.validators.conventions.policy.archetype import (
    TEMPLATES as POLICY_TEMPLATES,
    _SESSION_CONVENTION,
)

# The real convention source the policy/grammar freedom-layer variants read. Tracked,
# and NOT matched by E034's `*.convention.yaml`-under-src + `plan/**.yaml` residue globs
# only by luck of the name — the hook and pyproject faults are not matched at all.
_TRACKED_TARGET = _SESSION_CONVENTION


def _repo_root() -> Path:
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")


def _policy_template():
    return next(t for t in POLICY_TEMPLATES if t.template_id == "forbidden_construct_absence")


def _tracked_hashes(root: Path) -> dict:
    """sha256 of every file git tracks, keyed by path. The migrated families wrote git
    hooks, pyproject.toml and committed test sources — surfaces a YAML-only guard misses
    entirely — so the guard here is the whole tracked tree, not a YAML glob."""
    listing = subprocess.run(
        ["git", "ls-files", "-z"], cwd=root, capture_output=True, text=True, timeout=120,
    ).stdout
    out = {}
    for rel in listing.split("\0"):
        if not rel:
            continue
        p = root / rel
        if p.is_file():
            out[rel] = hashlib.sha256(p.read_bytes()).hexdigest()
    return out


@pytest.mark.convention_filesystem_mutation
def test_on_disk_fault_rewrites_the_checkout() -> None:
    """E035-RED-001: the retired on-disk mechanism mutates a TRACKED file mid-test.

    Proves the hazard the staged root removes. Inside policy ``_parity.overwrite_file``
    the targeted convention source differs from its byte-snapshot — a byte-identical-
    throughout guard would fail here — and after the ``finally`` it is restored. Kept as
    a live characterization so the retained on-disk oracle can never silently stop
    writing, exactly as E034 kept coherence's ``patch_file``.
    """
    root = _repo_root()
    target = root / _TRACKED_TARGET
    before = target.read_bytes()

    with policy_parity.overwrite_file(target, before.decode("utf-8") + "\n# fault\n"):
        during = target.read_bytes()

    after = target.read_bytes()
    assert during != before, (
        "on-disk fault did not rewrite the tracked file — the RED characterization is vacuous"
    )
    assert after == before, "on-disk fault left residue after its finally-revert"


def test_staged_root_carries_the_real_bytes_plus_the_fault(clean_convention_graph, tmp_path) -> None:
    """E035-GREEN-001: the staged tree is the real file's own bytes, plus the fault.

    This is what makes the redirect faithful rather than a re-implementation of the
    substrate in a fixture: the evaluator pointed at the temp root parses exactly what it
    would have parsed in the checkout, and the fault is the only difference.
    """
    root = _repo_root()
    real = (root / _TRACKED_TARGET).read_text(encoding="utf-8")

    staged = mirror_file(root, tmp_path, _TRACKED_TARGET, lambda t: t + "\n# injected\n")

    assert staged == tmp_path / _TRACKED_TARGET, "the mirror did not keep the real relative path"
    assert staged.read_text(encoding="utf-8") == real + "\n# injected\n"


def test_a_vacuous_fault_transform_raises(tmp_path) -> None:
    """E035-GREEN-001: a fault whose anchor has drifted must fail loudly, not pass.

    The on-disk helpers this replaces asserted the anchor by hand (`assert old in orig`)
    — and grammar's did not assert it at all, so a drifted anchor would have evaluated an
    UNFAULTED document and gone green while catching nothing. `mirror_file` makes that
    structurally impossible.
    """
    root = _repo_root()
    with pytest.raises(ValueError, match="vacuous"):
        mirror_file(root, tmp_path, _TRACKED_TARGET, lambda t: t)


def test_root_redirect_flags_the_fault_and_leaves_the_source_graph_clean(
    clean_convention_graph, tmp_path
) -> None:
    """E035-GREEN-001: a real root-reading evaluator flags a staged fault, and the shared
    session graph comes back with its ids AND its root unchanged."""
    root = _repo_root()
    ids_before = clean_convention_graph.ids()
    root_before = clean_convention_graph.root

    mirror_file(
        root, tmp_path, _TRACKED_TARGET,
        lambda t: t.replace(
            '      - "Bash(pytest:*)"', '      - "Bash(pytest:*)"\n      - "Bash(git push:*)"', 1
        ),
    )
    staged = graph_rooted_at(clean_convention_graph, tmp_path)

    flagged = _policy_template().evaluate(staged, {"variant": "freedom_layer_bash_scope"})
    assert any("git push" in v.get("matched_construct", "") for v in flagged), (
        f"the staged fault was not caught by the real evaluator: {flagged}"
    )
    # The same evaluator over the untouched session graph is silent.
    assert _policy_template().evaluate(
        clean_convention_graph, {"variant": "freedom_layer_bash_scope"}
    ) == []

    assert clean_convention_graph.ids() == ids_before, "the session graph's node ids changed"
    assert clean_convention_graph.root == root_before, (
        "the redirect leaked into the shared session graph's root — every later test would "
        "have evaluated against a temp tree"
    )


def test_rooted_clone_cannot_leak_a_node_into_the_session_graph(
    clean_convention_graph, tmp_path
) -> None:
    """E035-GREEN-001: `graph_rooted_at` copies `_nodes`/`_by_id` structurally, so a node
    added to the redirected graph is invisible to the session graph. A plain shallow copy
    would share those containers and `add_node` would corrupt every later test."""
    probe = "wmbt:validate-conventions:E999-e035-probe"
    staged = graph_rooted_at(clean_convention_graph, tmp_path)
    add_node(staged, id=probe, kind="wmbt", fields={"urn": probe})

    assert probe in staged.ids()
    assert probe not in clean_convention_graph.ids(), (
        "add_node on a rooted clone leaked into the shared session graph"
    )


def test_node_at_resolves_the_anchor_the_old_fault_wrote(clean_convention_graph) -> None:
    """E035-GREEN-001: `node_at` maps the FILE the old fault rewrote to the node the new
    fault mutates, so the anchor survives the migration and a moved file raises."""
    wagon = node_at(
        clean_convention_graph,
        "plan/freeze_runtime_contracts/_freeze_runtime_contracts.yaml",
    )
    assert wagon.kind == "wagon"
    assert wagon.fields.get("wagon") == "freeze-runtime-contracts"

    with pytest.raises(KeyError):
        node_at(clean_convention_graph, "plan/no_such_wagon/_no_such_wagon.yaml")


def test_migrated_families_write_nothing_to_the_tracked_tree(clean_convention_graph, tmp_path) -> None:
    """E035-GREEN-001: staging + redirecting writes only under tmp_path.

    The whole tracked tree — not just YAML — is byte-identical across a staged injection
    that touches the three surfaces the migrated families used to rewrite.
    """
    root = _repo_root()
    before = _tracked_hashes(root)

    mirror_file(root, tmp_path, "pyproject.toml", lambda t: t.replace(', "nodes/*.yaml"', "", 1))
    mirror_file(root, tmp_path, _TRACKED_TARGET, lambda t: t + "\n# injected\n")
    stage_file(tmp_path, "src/atdd/_probe.py", "x = 1\n")

    assert _tracked_hashes(root) == before, (
        "a tracked file changed during a staged-root injection — something wrote the checkout"
    )
