# Component: component:author-atdd-substrate:substrate-spine:AuthorVariant:backend:application
"""Scaffold a convention-graph **variant** alongside an authored rule node (#1212).

When `atdd author convention-node` writes a rule node that carries a validator
binding (`implementation.ref`), the new convention is *declared* but not yet
*enforced by the engine*. This module closes that gap: given a registered
`(family, template)` pair, it scaffolds a runnable convention-validator variant
under `src/atdd/validators/conventions/<family>/test_<variant>.py`, instantiating
the family/template against the composed convention graph.

A brand-new rule cannot execute real graph traversal or claim legacy parity yet,
so the scaffold is an *honest* RED-phase artifact: its contract test (template
registration + failure-evidence + implementation binding) PASSES, while the
real-traversal test is `xfail`-marked (strict) — never fake-green, never
fabricated parity. The family/template pair is validated against the real
`registry.yaml`, and the template metadata (question/selector/traversal/…) is
read from the family `archetype.py` — both resolved from the installed
`atdd.validators.conventions` package, independent of the write root.

Scope: read-only against the engine; the only write is a NEW variant file. An
existing variant file is never clobbered (idempotent).
"""
from __future__ import annotations

import importlib
import re
from pathlib import Path

import yaml

from atdd.planner.commands.author import AuthorInputError

_CONV_PKG = "atdd.validators.conventions"


def _conventions_pkg_dir() -> Path:
    """Filesystem dir of the installed ``atdd.validators.conventions`` package.

    The registry + family archetypes are read from here (the real engine), not
    from the write ``root`` — so a tmp-root smoke still validates against the
    canonical families while writing the scaffold into the tmp tree.
    """
    pkg = importlib.import_module(_CONV_PKG)
    return Path(pkg.__file__).resolve().parent


def load_registry() -> dict[str, list[str]]:
    """Return ``{family_id: [template_id, ...]}`` from the engine's registry.yaml."""
    path = _conventions_pkg_dir() / "registry.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {
        fam["id"]: [t["id"] for t in fam.get("templates", [])]
        for fam in data.get("families", [])
    }


def validate_family_template(family: str, template: str) -> None:
    """Reject an unknown family or an unregistered ``(family, template)`` pair.

    Raises ``AuthorInputError`` (``.field`` = ``"family"`` or ``"template"``).
    """
    families = load_registry()
    if family not in families:
        raise AuthorInputError(
            "family",
            f"unknown convention family {family!r}; registered: "
            f"{', '.join(sorted(families))}",
        )
    if template not in families[family]:
        raise AuthorInputError(
            "template",
            f"template {template!r} is not registered under family {family!r}; "
            f"templates: {', '.join(families[family]) or '(none)'}",
        )


def _load_template_contract(family: str, template: str):
    """Return the ``TemplateContract`` for ``template`` from the family archetype.

    The pair is registry-validated first, so a missing archetype/template here is
    an engine inconsistency, surfaced as ``AuthorInputError(field="template")``.
    """
    archetype = importlib.import_module(f"{_CONV_PKG}.{family}.archetype")
    for contract in getattr(archetype, "TEMPLATES", []):
        if contract.template_id == template:
            return contract
    raise AuthorInputError(
        "template",
        f"template {template!r} registered for {family!r} but absent from its "
        f"archetype TEMPLATES — engine inconsistency",
    )


def derive_variant(rule_id: str) -> str:
    """Derive a unique snake_case variant slug from a canonical rule_id.

    ``coder.green.demo-x`` -> ``coder_green_demo_x``. Using the *whole* rule_id
    (not just the last segment) keeps the variant collision-free across roles
    and phases, so the per-variant file name is a stable idempotency key.
    """
    return re.sub(r"[^a-z0-9]+", "_", rule_id.lower()).strip("_")


def variant_home(family: str, root: Path | str) -> Path:
    """Canonical family-validator dir under the write ``root`` (spec engine path)."""
    return Path(root) / "src" / "atdd" / "validators" / "conventions" / family


def _py_str(value: str) -> str:
    """Render a string as a safely-quoted Python literal (handles apostrophes)."""
    return repr(value)


def render_variant(
    *,
    family: str,
    template: str,
    variant: str,
    rule_id: str,
    implementation_ref: str,
    contract,
    legacy_parity_sources: list[str] | None = None,
) -> str:
    """Render the RED-phase variant module source for a brand-new rule.

    The contract test asserts only facts that are genuinely true at scaffold
    time (template is registered; failure-evidence + binding are present); the
    real selector->traversal->invariant differential is left as a strict-xfail
    stub the rule's author replaces when the evaluator is implemented.
    """
    legacy = list(legacy_parity_sources or [])
    evidence = list(contract.failure_evidence)
    contract_test = f"test_{variant}_variant_contract"
    pending_test = f"test_{variant}_real_traversal_pending"

    return f'''\
# URN: test:validate-conventions:{family}-variants:{variant}
# Rule: {rule_id}
# Phase: RED
# Layer: integration
# Assertion: behavioral
"""Convention validator variant `{family}/{variant}` — scaffolded by `atdd author` (#1212).

Instantiates the `{family}/{template}` template against the composed convention
graph for the newly-authored rule `{rule_id}` (binding: `{implementation_ref}`).

RED-phase scaffold (honest): the variant *contract* below — template is
registered in the family archetype, failure-evidence + implementation binding
are declared — is asserted and PASSES. Real graph traversal and legacy-parity
differential are NOT yet wired; the `{pending_test}` test is a strict-xfail
placeholder (NOT fake-green, NO fabricated parity). When the rule's evaluator is
implemented, replace that stub with a real selector->traversal->invariant
assertion over the composed graph and flip the header to `Phase: GREEN`.
"""
from __future__ import annotations

import pytest

from {_CONV_PKG}.{family}.archetype import TEMPLATE_IDS

FAMILY = {_py_str(family)}
TEMPLATE = {_py_str(template)}
VARIANT = {_py_str(variant)}
RULE_ID = {_py_str(rule_id)}
IMPLEMENTATION_REF = {_py_str(implementation_ref)}
QUESTION = {_py_str(contract.question)}
SELECTOR = {_py_str(contract.selector)}
TRAVERSAL = {_py_str(contract.traversal)}
INVARIANT = {_py_str(contract.invariant)}
AUTO_CAPTURE = {_py_str(contract.auto_capture)}
FAILURE_EVIDENCE = {evidence!r}
# Brand-new rule: no legacy validator to claim parity against (parity is proven
# when the evaluator lands). An empty list is the honest record — NOT fabricated.
LEGACY_PARITY_SOURCES: list[str] = {legacy!r}


def {contract_test}() -> None:
    assert TEMPLATE in TEMPLATE_IDS, f"{{TEMPLATE}} not in {{FAMILY}} archetype"
    assert set(FAILURE_EVIDENCE), "variant must declare failure evidence fields"
    assert IMPLEMENTATION_REF, "variant must bind to a validator implementation ref"


@pytest.mark.xfail(strict=True, reason="RED: real graph traversal not yet wired for " + RULE_ID)
def {pending_test}() -> None:
    # Replace with a real selector->traversal->invariant assertion over the
    # composed convention graph + a function-level legacy-parity differential
    # once the evaluator for RULE_ID is implemented, then drop this xfail.
    pytest.fail("real traversal/parity not yet implemented for " + RULE_ID)
'''


def scaffold_variant(
    *,
    family: str,
    template: str,
    rule_id: str,
    implementation_ref: str,
    root: Path | str,
    legacy_parity_sources: list[str] | None = None,
) -> Path:
    """Scaffold the convention-graph variant for ``rule_id``; return its path.

    Validates the ``(family, template)`` pair against the engine registry, reads
    the template metadata from the family archetype, and writes a RED-phase
    variant module under ``<root>/src/atdd/validators/conventions/<family>/``.
    Idempotent: an existing variant file is returned untouched (never clobbered).
    """
    if not implementation_ref:
        raise AuthorInputError(
            "implementation",
            "variant scaffolding needs a validator binding (implementation.ref)",
        )
    validate_family_template(family, template)
    contract = _load_template_contract(family, template)
    variant = derive_variant(rule_id)
    path = variant_home(family, root) / f"test_{variant}.py"
    if path.exists():
        return path  # idempotent — do not clobber an existing variant
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        render_variant(
            family=family,
            template=template,
            variant=variant,
            rule_id=rule_id,
            implementation_ref=implementation_ref,
            contract=contract,
            legacy_parity_sources=legacy_parity_sources,
        ),
        encoding="utf-8",
    )
    return path
