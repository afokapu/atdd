# URN: test:author-atdd-substrate:author-convention-node:variant-scaffold-unit
# Issue: #1212
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""Unit coverage for the convention-graph variant scaffolder (#1212).

`atdd author convention-node --family/--template` scaffolds a runnable
convention-validator variant alongside the rule node so the new convention is
enforced by the engine, not merely declared. These tests pin the scaffolder's
contract: a variant is written under the family dir, derived from the rule_id,
honest (RED-phase, no fabricated parity), idempotent, and rejecting of an
unknown family/template pair.
"""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_variant import (
    derive_variant,
    scaffold_variant,
    validate_family_template,
)


def test_derive_variant_is_unique_snake_case() -> None:
    # whole rule_id (not just last segment) -> collision-free snake_case slug
    assert derive_variant("coder.green.demo-x") == "coder_green_demo_x"
    assert derive_variant("planner.smoke.feedback-loop") == "planner_smoke_feedback_loop"


def test_scaffold_writes_runnable_variant_under_family(tmp_path) -> None:
    path = scaffold_variant(
        family="grammar",
        template="identifier_grammar_conformance",
        rule_id="coder.green.demo-x",
        implementation_ref="test_x::test_y",
        root=tmp_path,
    )
    assert path == (
        tmp_path / "src" / "atdd" / "validators" / "conventions" / "grammar"
        / "test_coder_green_demo_x.py"
    )
    src = path.read_text(encoding="utf-8")
    # honest RED-phase scaffold: marked RED, imports the family archetype, binds
    # the rule's implementation ref, and fabricates NO legacy parity.
    assert "# Phase: RED" in src
    assert "from atdd.validators.conventions.grammar.archetype import TEMPLATE_IDS" in src
    assert "IMPLEMENTATION_REF = 'test_x::test_y'" in src
    assert "LEGACY_PARITY_SOURCES: list[str] = []" in src
    # metadata is read from the archetype, not invented
    assert "QUESTION = 'Does an identifier" in src
    assert "FAILURE_EVIDENCE = ['node_id'" in src


def test_scaffold_is_idempotent_never_clobbers(tmp_path) -> None:
    first = scaffold_variant(
        family="grammar", template="identifier_grammar_conformance",
        rule_id="coder.green.demo-x", implementation_ref="test_x::test_y", root=tmp_path,
    )
    sentinel = "# operator edit preserved\n"
    first.write_text(first.read_text(encoding="utf-8") + sentinel, encoding="utf-8")
    second = scaffold_variant(
        family="grammar", template="identifier_grammar_conformance",
        rule_id="coder.green.demo-x", implementation_ref="test_x::test_y", root=tmp_path,
    )
    assert second == first
    assert first.read_text(encoding="utf-8").endswith(sentinel), "must not clobber existing variant"


def test_rejects_unknown_family(tmp_path) -> None:
    with pytest.raises(AuthorInputError) as exc:
        scaffold_variant(
            family="does-not-exist", template="whatever",
            rule_id="coder.green.demo-x", implementation_ref="r::t", root=tmp_path,
        )
    assert exc.value.field == "family"


def test_rejects_template_not_registered_under_family(tmp_path) -> None:
    with pytest.raises(AuthorInputError) as exc:
        # grammar is a real family, but this template belongs to another family
        scaffold_variant(
            family="grammar", template="node_schema_conformance",
            rule_id="coder.green.demo-x", implementation_ref="r::t", root=tmp_path,
        )
    assert exc.value.field == "template"


def test_rejects_missing_implementation_ref(tmp_path) -> None:
    with pytest.raises(AuthorInputError) as exc:
        scaffold_variant(
            family="grammar", template="identifier_grammar_conformance",
            rule_id="coder.green.demo-x", implementation_ref="", root=tmp_path,
        )
    assert exc.value.field == "implementation"


def test_validate_family_template_accepts_registered_pair() -> None:
    # no raise == accepted
    validate_family_template("grammar", "identifier_grammar_conformance")
