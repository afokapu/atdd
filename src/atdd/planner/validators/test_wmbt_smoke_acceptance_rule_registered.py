# Acceptance: acc:govern-lifecycle:E921-UNIT-001-wmbt-smoke-acceptance-rule-registered-in-convention
"""
Asserts the rule ``planner.wmbt.must-have-smoke-acceptance`` is registered in
its canonical home: ``src/atdd/planner/conventions/wmbt.convention.yaml``.

Background (#921 — split from #919 Section A discussion): the prior
template-reader test (``test_e015_unit_002::test_atdd_md_names_must_have_smoke_acceptance_rule``)
asserted the rule id string appeared in ``CONDUCTOR.md``. That was the wrong
substrate check — duplicating convention rule IDs into the agent-facing
template re-introduced the dual-source-of-truth pattern the Coach
Decomposition (#887) was actively removing (phase_machine was already excised
from the template in #888 for the same reason).

The rule lives in ``wmbt.convention.yaml``; this test asserts that fact
directly. The companion installed-package smoke test asserts the rule survives
the build-and-install pipeline.

Convention: ``src/atdd/planner/conventions/wmbt.convention.yaml``
"""
from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

import yaml

RULE_ID = "planner.wmbt.must-have-smoke-acceptance"
_CONVENTION_FILENAME = "wmbt.convention.yaml"


def _load_convention(conv_path: Path) -> dict[str, Any]:
    assert conv_path.exists(), f"Convention not found: {conv_path}"
    return yaml.safe_load(conv_path.read_text())


def _rule_ids(convention: dict[str, Any]) -> set[str]:
    return {r["id"] for r in convention.get("rules", []) if isinstance(r, dict) and "id" in r}


def test_wmbt_convention_registers_must_have_smoke_acceptance_rule() -> None:
    """The local source-tree convention YAML registers the rule id."""
    conv_path = (
        Path(__file__).parent.parent  # src/atdd/planner
        / "conventions"
        / _CONVENTION_FILENAME
    )
    rule_ids = _rule_ids(_load_convention(conv_path))
    assert RULE_ID in rule_ids, (
        f"Rule '{RULE_ID}' is missing from {conv_path}. "
        f"Rules currently registered: {sorted(rule_ids)}. "
        "Add the rule to the convention's `rules:` block — "
        "do NOT add it back to CONDUCTOR.md (that would re-introduce the "
        "dual-source-of-truth pattern removed by the Coach Decomposition #887)."
    )


def test_installed_wmbt_convention_ships_must_have_smoke_acceptance_rule() -> None:
    """SMOKE: the rule ships in the installed-package convention YAML.

    This replaces the prior ``test_installed_atdd_md_has_rule_id`` (which read
    ``CONDUCTOR.md`` from the installed package). The rule's canonical home is
    the convention YAML; that's what should ship.
    """
    # ``atdd.planner.conventions`` is a namespace package, so __file__ is None
    # and we resolve the directory via __path__.
    conventions_module = importlib.import_module("atdd.planner.conventions")
    conv_dir = Path(next(iter(conventions_module.__path__)))
    conv_path = conv_dir / _CONVENTION_FILENAME
    rule_ids = _rule_ids(_load_convention(conv_path))
    assert RULE_ID in rule_ids, (
        f"Installed package convention {conv_path} does not register '{RULE_ID}'. "
        "The fix did not ship into the installed distribution."
    )
