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
import os
import subprocess
import sys
from pathlib import Path
from typing import List

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
    raise RuntimeError("repo root not found")


def _graph(root: Path):
    from atdd.validators.conventions._support.graph_loader import load_composed_graph

    return load_composed_graph(root)


def evaluate(template_id: str, variant: str, root: Path) -> List[dict]:
    """Official variant execution path: real composed graph -> template.evaluate."""
    return _TEMPLATES[template_id].evaluate(_graph(root), config={"variant": variant})


@contextlib.contextmanager
def _rename_rule_id(conv_path: Path, rule_id: str):
    orig = conv_path.read_text(encoding="utf-8")
    quoted = f'"{rule_id}"'
    if quoted not in orig:
        raise AssertionError(
            f'rule id {quoted} not found verbatim in {conv_path} — convention drifted'
        )
    conv_path.write_text(orig.replace(quoted, f'"{rule_id}-PARITYBROKEN"', 1), encoding="utf-8")
    try:
        yield
    finally:
        conv_path.write_text(orig, encoding="utf-8")


def _legacy_caught(root: Path, nodeid: str) -> bool:
    """Run the legacy validator in a subprocess (no import). rc != 0 => caught."""
    rc = subprocess.run(
        [sys.executable, "-m", "pytest", nodeid, "-q", "-p", "no:cacheprovider"],
        cwd=root,
        env={"PYTHONPATH": "src", "PATH": os.environ["PATH"]},
        capture_output=True,
        text=True,
    ).returncode
    return rc != 0


def assert_clean_baseline(variant: str, root: Path) -> None:
    """Both binding templates must flag nothing on the real repo for this variant."""
    for tid in (_FORWARD, _ROUNDTRIP):
        flags = evaluate(tid, variant, root)
        assert flags == [], f"{variant}: {tid} flagged the clean repo: {flags[:3]}"


def assert_fault_parity(
    variant: str, conv_rel: str, rule_id: str, legacy_nodeid: str, root: Path
) -> dict:
    """Inject the binding fault, prove BOTH paths catch it, revert. Returns the
    measured parity verdict (never assumes it — the brief's honesty rule)."""
    conv_path = root / conv_rel
    assert conv_path.exists(), f"convention not found: {conv_path}"

    # pre-state: convention roundtrip clean
    assert evaluate(_ROUNDTRIP, variant, root) == [], f"{variant}: dirty before injection"

    with _rename_rule_id(conv_path, rule_id):
        conv_flags = evaluate(_ROUNDTRIP, variant, root)
        legacy_caught = _legacy_caught(root, legacy_nodeid)

    # post-revert: clean again (no residue)
    assert evaluate(_ROUNDTRIP, variant, root) == [], f"{variant}: residue after revert"

    conv_caught = bool(conv_flags)
    verdict = {
        (True, True): "both",
        (True, False): "convention-only",
        (False, True): "legacy-only",
        (False, False): "neither",
    }[(legacy_caught, conv_caught)]

    # Parity is the wiring goal — assert it (the measurement above is honest; if a
    # variant could NOT reach `both`, this assertion is where it would surface).
    assert verdict == "both", (
        f"{variant}: legacy/convention parity not achieved (verdict={verdict}; "
        f"legacy_caught={legacy_caught}, convention_caught={conv_caught})"
    )

    # evidence keys must be a strict subset of the template's failure_evidence
    allowed = set(_TEMPLATES[_ROUNDTRIP].failure_evidence)
    for ev in conv_flags:
        assert set(ev) <= allowed, (
            f"{variant}: evidence keys {set(ev)} not subset of {sorted(allowed)}"
        )

    # the flagged binding break must be the injected rule, not collateral
    broken = f"{rule_id}-PARITYBROKEN"
    assert any(ev.get("declaration_id") == broken for ev in conv_flags), (
        f"{variant}: convention flagged something other than the injected rule: {conv_flags[:3]}"
    )

    return {"verdict": verdict, "convention_flags": len(conv_flags)}
