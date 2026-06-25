# URN: urn:atdd:test:coach:utils:rule_validator_resolver
# WMBT: wmbt:govern-lifecycle:rule-validator-resolution
# Issue: #399

"""Unit tests for ``atdd.coach.utils.rule_validator_resolver``.

The resolver is the seam between a rule's ``validator: <module>::<func>``
string and the AST of the validator function that binds the rule. It
must:

* Parse ``module::function`` strings.
* Infer the validator path from archetype + module basename.
* AST-parse the validator file as TEXT (no import).
* Surface the set of literal ``bind_rule("<id>")`` arguments inside the
  function body (and at module level).
* Fail loudly with ``ValidatorResolutionError`` when the file is missing
  or the function name is wrong.
"""

from __future__ import annotations

import ast
import textwrap
from pathlib import Path
from unittest import mock

import pytest

from atdd.coach.utils.rule_validator_resolver import (
    ResolvedValidator,
    ValidatorResolutionError,
    infer_module_path,
    parse_validator_field,
    resolve_validator,
)


pytestmark = [pytest.mark.coach]


# ---------------------------------------------------------------------------
# parse_validator_field
# ---------------------------------------------------------------------------
def test_parse_valid_field():
    module, func = parse_validator_field("test_dead_code_python::test_no_unreachable_definitions")
    assert module == "test_dead_code_python"
    assert func == "test_no_unreachable_definitions"


def test_parse_rejects_missing_separator():
    with pytest.raises(ValueError):
        parse_validator_field("test_dead_code_python")


def test_parse_rejects_empty_module():
    with pytest.raises(ValueError):
        parse_validator_field("::test_x")


def test_parse_rejects_empty_function():
    with pytest.raises(ValueError):
        parse_validator_field("test_x::")


def test_parse_rejects_non_string():
    with pytest.raises(ValueError):
        parse_validator_field(None)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# infer_module_path
# ---------------------------------------------------------------------------
def test_infer_rejects_unknown_archetype(tmp_path: Path):
    with pytest.raises(ValidatorResolutionError):
        infer_module_path("frontend", "anything")


def test_infer_rejects_missing_file():
    with pytest.raises(ValidatorResolutionError):
        infer_module_path("coder", "this_module_does_not_exist")


# ---------------------------------------------------------------------------
# resolve_validator (with a synthetic module under a patched _ATDD_PKG_DIR)
# ---------------------------------------------------------------------------
@pytest.fixture
def fake_pkg(tmp_path: Path, monkeypatch):
    """Build a fake atdd package layout under tmp_path and patch the resolver."""
    pkg = tmp_path / "atdd"
    (pkg / "coder" / "validators").mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "coder" / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "coder" / "validators" / "__init__.py").write_text("", encoding="utf-8")
    monkeypatch.setattr(
        "atdd.coach.utils.rule_validator_resolver._ATDD_PKG_DIR", pkg
    )
    return pkg


def _write_validator(pkg: Path, archetype: str, name: str, body: str) -> Path:
    target = pkg / archetype / "validators" / f"{name}.py"
    target.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return target


def test_resolve_returns_function_node(fake_pkg: Path):
    _write_validator(
        fake_pkg, "coder", "test_demo",
        '''
        from atdd.coach.utils.rule_binding import bind_rule

        _RULE = bind_rule("coder.demo.thing")

        def test_thing():
            assert True
        ''',
    )

    resolved = resolve_validator(
        archetype="coder",
        validator_field="test_demo::test_thing",
    )

    assert isinstance(resolved, ResolvedValidator)
    assert resolved.module_basename == "test_demo"
    assert resolved.function_name == "test_thing"
    assert resolved.archetype == "coder"
    assert isinstance(resolved.function_node, ast.FunctionDef)
    assert "coder.demo.thing" in resolved.bound_rule_ids


def test_resolve_collects_function_level_bind_rule(fake_pkg: Path):
    _write_validator(
        fake_pkg, "coder", "test_local",
        '''
        def test_x():
            from atdd.coach.utils.rule_binding import bind_rule
            meta = bind_rule("coder.demo.local")
            assert meta is not None
        ''',
    )
    resolved = resolve_validator(
        archetype="coder",
        validator_field="test_local::test_x",
    )
    assert "coder.demo.local" in resolved.bound_rule_ids


def test_resolve_function_not_found(fake_pkg: Path):
    _write_validator(
        fake_pkg, "coder", "test_missing",
        '''
        def test_other():
            pass
        ''',
    )
    with pytest.raises(ValidatorResolutionError):
        resolve_validator(
            archetype="coder",
            validator_field="test_missing::test_x",
        )


def test_resolve_handles_syntax_error(fake_pkg: Path):
    target = fake_pkg / "coder" / "validators" / "test_bad.py"
    target.write_text("def broken(:\n    pass\n", encoding="utf-8")
    with pytest.raises(ValidatorResolutionError):
        resolve_validator(
            archetype="coder",
            validator_field="test_bad::broken",
        )


def test_resolve_ignores_non_literal_bind_rule_args(fake_pkg: Path):
    _write_validator(
        fake_pkg, "coder", "test_dynamic",
        '''
        def test_x():
            rid = "coder.demo.dynamic"
            from atdd.coach.utils.rule_binding import bind_rule
            bind_rule(rid)
        ''',
    )
    resolved = resolve_validator(
        archetype="coder",
        validator_field="test_dynamic::test_x",
    )
    # Variable references are not literals; the resolver tracks ONLY
    # literal string arguments.
    assert resolved.bound_rule_ids == set()


# ---------------------------------------------------------------------------
# convention-variant targets (#1207): a rule's validator/implementation.ref may
# resolve to a convention-graph variant under
# src/atdd/validators/conventions/<family>/<stem>.py via the
# `conventions/<family>/<stem>::<func>` form. Such a target binds via parity/
# execution, NOT a bind_rule literal — so is_convention is flagged and an empty
# bound_rule_ids is acceptable.
# ---------------------------------------------------------------------------
def _write_convention_variant(pkg: Path, family: str, name: str, body: str) -> Path:
    target = pkg / "validators" / "conventions" / family / f"{name}.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    return target


def test_resolve_convention_variant_target(fake_pkg: Path):
    _write_convention_variant(
        fake_pkg, "resolution", "test_train_registry_spec_exists",
        '''
        FAMILY = "resolution"
        VARIANT = "train_registry_spec_exists"
        LEGACY_PARITY_SOURCES = ["src/atdd/planner/validators/test_train_validation.py"]

        def test_fault_injection():
            assert True
        ''',
    )
    resolved = resolve_validator(
        archetype="planner",
        validator_field="conventions/resolution/test_train_registry_spec_exists::test_fault_injection",
    )
    assert isinstance(resolved, ResolvedValidator)
    assert resolved.is_convention is True
    assert resolved.function_name == "test_fault_injection"
    assert isinstance(resolved.function_node, ast.FunctionDef)
    # Convention variants enforce via parity, not bind_rule — empty is OK.
    assert resolved.bound_rule_ids == set()


def test_resolve_convention_target_missing_file_raises(fake_pkg: Path):
    with pytest.raises(ValidatorResolutionError):
        resolve_validator(
            archetype="planner",
            validator_field="conventions/resolution/test_does_not_exist::test_x",
        )


def test_resolve_convention_target_missing_function_raises(fake_pkg: Path):
    _write_convention_variant(
        fake_pkg, "schema", "test_demo_variant",
        '''
        def test_present():
            assert True
        ''',
    )
    with pytest.raises(ValidatorResolutionError):
        resolve_validator(
            archetype="planner",
            validator_field="conventions/schema/test_demo_variant::test_absent",
        )


# ---------------------------------------------------------------------------
# reverse-coherence acceptance (#1207): an enforced rule whose `validator:` names
# a convention variant binds via parity, so reverse coherence must NOT demand a
# bind_rule literal. (Lives here, NOT under */validators/, so the rule_id literal
# below is not scanned as a production emission by rule_id_registry_coherence.)
# ---------------------------------------------------------------------------
def test_convention_variant_target_satisfies_reverse_coherence(monkeypatch):
    from atdd.coach.utils.rule_id_registry import RuleMetadata
    import atdd.coach.validators.test_rule_validator_binding as binding

    fake = {
        "planner.train.registry": RuleMetadata(
            rule_id="planner.train.registry",
            convention_path=Path(
                "src/atdd/planner/conventions/nodes/planner.train.registry.convention.yaml"
            ),
            description="registry entry -> spec file existence",
            disposition="strict",
            validator="conventions/resolution/test_train_validation::test_fault_injection_and_legacy_parity",
        )
    }
    monkeypatch.setattr(binding, "build_registry", lambda: fake)
    assert binding._build_violations() == []
