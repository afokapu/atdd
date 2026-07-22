# URN: component:validate-conventions:binding-variants:parity-support:backend:domain
# Runtime: python
# Purpose: Shared executable legacy-parity harness for binding-family variant wiring (#1212).
"""Executable legacy-parity harness for the `binding` family's remaining variants.

Every binding variant proves the SAME shape end-to-end against the REAL composed
convention graph (`_support.graph_loader.load_composed_graph`), executed through
the official template path (`archetype.TEMPLATES[*].evaluate(graph, config)`):

  * clean baseline — the family's binding templates flag NOTHING on the real repo
    (a vacuous pass is impossible: the baseline is asserted == []).
  * fault injection + legacy parity — rename the variant's `rule_id` in its
    convention (a genuine declaration<->implementation roundtrip break: the rule
    now declares a `validator:` that no longer emits its id), then assert BOTH
      - the convention path (`emitted_identity_roundtrip` template), AND
      - the named legacy reverse-coherence binder (run in a SUBPROCESS — never
        imported, so the variant stays parallel-safe and free of persona-validator
        imports)
    catch it; then revert and re-assert the baseline is clean again.

The legacy validators (`test_no_hardcoded_rule_severity`,
`test_commit_trailers_binding`, `test_e001_unit_001_spawn_cli_launches_session`,
`test_e009_unit_001_convention_declares_runtime_artifacts_rule`) each call
`bind_rule(<id>)` against the original id, so renaming the convention's `id:`
makes that binding fail — the differential is real, not faked.
"""
from __future__ import annotations

import contextlib
from pathlib import Path
from typing import List

from atdd.validators.conventions._support.graph_mutations import (
    clone_graph,
    rename_rule_id,
)
from atdd.validators.conventions.binding.archetype import TEMPLATES

_TEMPLATES = {t.template_id: t for t in TEMPLATES}
_ROUNDTRIP = "emitted_identity_roundtrip"
_FORWARD = "declaration_to_implementation_binding"


def repo_root() -> Path:
    """Resolve the toolkit repo root (pyproject.toml + .atdd), mirroring the
    conventions `tests/conftest.py` fixture so these variant modules — which live
    OUTSIDE the tests/ folder — are self-contained."""
    p = Path(__file__).resolve()
    for parent in p.parents:
        if (parent / "pyproject.toml").exists() and (parent / ".atdd").exists():
            return parent
    raise RuntimeError("repo root not found")  # atdd:suppress(coach.code-roots.resolver-degrades-not-raises) — #1499 ratchet: pre-existing raising resolver; destination is zero


def _graph(root: Path):
    from atdd.validators.conventions._support.graph_loader import load_composed_graph

    return load_composed_graph(root)


def evaluate(template_id: str, variant: str, root: Path, graph=None) -> List[dict]:
    """Official variant execution path: real composed graph -> template.evaluate.

    ``graph`` lets a read-only caller pass the session-scoped clean graph (#1414).
    Callers that have mutated the tree must omit it so the graph is re-read.
    """
    g = graph if graph is not None else _graph(root)
    return _TEMPLATES[template_id].evaluate(g, config={"variant": variant})


@contextlib.contextmanager
def _rename_rule_id_on_disk(conv_path: Path, rule_id: str):
    """Rewrite a rule id in a real ``*.convention.yaml`` on disk, reverting in ``finally``.

    ⚠️ This MUTATES the working tree. It is retained ONLY as a characterization oracle for
    the old fault-injection mechanism (E033-RED) — proving the on-disk write is what the
    in-memory path (``graph_mutations``) removes. Template-evaluator fault tests must NOT
    use it; they inject into a cloned graph instead (see ``assert_fault_convention_only``).
    """
    orig = conv_path.read_text(encoding="utf-8")
    quoted = f'"{rule_id}"'
    # single-node nodes/ form: top-level `rule_id: <id>` (unquoted), anchored to a
    # line start so it does not match the `  legacy_rule_id:` provenance field (#1225).
    bare = f"\nrule_id: {rule_id}\n"
    if quoted in orig:
        broken = orig.replace(quoted, f'"{rule_id}-PARITYBROKEN"', 1)
    elif bare in orig:
        broken = orig.replace(bare, f"\nrule_id: {rule_id}-PARITYBROKEN\n", 1)
    else:
        raise AssertionError(
            f'rule id {rule_id!r} not found (as "{rule_id}" or top-level rule_id:) '
            f'in {conv_path} — convention drifted'
        )
    conv_path.write_text(broken, encoding="utf-8")
    try:
        yield
    finally:
        conv_path.write_text(orig, encoding="utf-8")


def assert_clean_baseline(variant: str, root: Path, graph=None) -> None:
    """Both binding templates must flag nothing on the real repo for this variant."""
    for tid in (_FORWARD, _ROUNDTRIP):
        flags = evaluate(tid, variant, root, graph=graph)
        assert flags == [], f"{variant}: {tid} flagged the clean repo: {flags[:3]}"


def assert_fault_convention_only(
    variant: str, conv_rel: str, rule_id: str, root: Path, graph=None
) -> dict:
    """Inject the binding fault into a CLONE of the clean graph, prove the roundtrip
    template catches it — with NO filesystem write and NO revert (#1415).

    ``graph`` is the session-scoped clean graph (#1414); pass it so the clone is deep-copied
    in memory instead of rebuilt. The fault is injected by :func:`rename_rule_id` on the
    clone: the rule's declaration id moves while its ``bind_rule`` emission stays put — the
    same declaration<->implementation break the old on-disk ``rule_id:`` rewrite produced,
    but the working tree (and the shared clean graph) are provably untouched.

    The legacy parity oracle has been decommissioned (#1207); the variant's own real-graph
    fault injection here + its clean baseline are the live coverage.
    """
    conv_path = root / conv_rel
    # Coherence only — asserts the convention that DECLARES the rule still exists; the file
    # is never opened or written. Guards against a convention being moved out from under a
    # variant (which would otherwise make the fault silently un-injectable).
    assert conv_path.exists(), f"convention not found: {conv_path}"

    clean = graph if graph is not None else _graph(root)

    # pre-state: the clean graph's roundtrip flags nothing for this variant
    assert evaluate(_ROUNDTRIP, variant, root, graph=clean) == [], (
        f"{variant}: dirty before injection"
    )

    faulted = clone_graph(clean)
    broken = rename_rule_id(faulted, rule_id)
    conv_flags = evaluate(_ROUNDTRIP, variant, root, graph=faulted)

    # the shared clean graph must be provably unmutated by the injection
    ids = clean.ids()
    assert rule_id in ids and broken not in ids, (
        f"{variant}: injection leaked into the shared clean graph (id {rule_id!r})"
    )

    assert conv_flags, f"{variant}: convention path missed the injected binding break"

    # evidence keys must be a strict subset of the template's failure_evidence
    allowed = set(_TEMPLATES[_ROUNDTRIP].failure_evidence)
    for ev in conv_flags:
        assert set(ev) <= allowed, (
            f"{variant}: evidence keys {set(ev)} not subset of {sorted(allowed)}"
        )

    # the flagged binding break must be the injected rule, not collateral
    assert any(ev.get("declaration_id") == broken for ev in conv_flags), (
        f"{variant}: convention flagged something other than the injected rule: {conv_flags[:3]}"
    )

    return {"convention_flags": len(conv_flags)}
