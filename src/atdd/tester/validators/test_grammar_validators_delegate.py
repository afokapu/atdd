# Component: component:test:grammar-delegation:GrammarValidatorsDelegate:backend:tests
# Runtime: python
# Purpose: The 6 grammar hard-coder validators are superseded onto URNGrammar — no local train-grammar literal survives, and typed identities are accepted (#1421).
"""Supersession proof for the grammar hard-coder validators (issue #1421).

Decision 8 of #1421: do NOT re-hard-code the URN grammar in N validators —
single-source it through the engine. These tests lock that in two ways:

1. **No second representation.** None of the six superseded validators may carry
   a hard-coded 4-digit train-grammar literal (``\\d{4}``); the train/journey
   grammar lives once, in ``urn_grammar.yaml``, executed by ``URNGrammar``.
2. **Engine-backed behaviour.** The delegating helpers each accept the identities
   the engine accepts (including the typed ``train:<subject>:<slug>`` family) and
   reject garbage — proving they call the engine, not a local regex.
"""
from __future__ import annotations

import importlib
from pathlib import Path

import pytest

_VALIDATOR_DIR = Path(__file__).resolve().parent

_SUPERSEDED = [
    "test_urn_spec_v3",
    "test_typescript_test_naming",
    "test_typescript_test_structure",
    "test_train_backend_e2e",
    "test_train_frontend_python",
    "test_train_frontend_e2e",
]


@pytest.mark.parametrize("mod_name", _SUPERSEDED)
def test_no_hardcoded_train_grammar_literal(mod_name: str) -> None:
    """No superseded validator re-encodes the 4-digit train grammar locally."""
    text = (_VALIDATOR_DIR / f"{mod_name}.py").read_text(encoding="utf-8")
    assert r"\d{4}" not in text, (
        f"{mod_name}.py still hard-codes a train-grammar literal (\\d{{4}}); "
        f"delegate to URNGrammar instead (issue #1421 Decision 8)."
    )


def test_spec_v3_train_header_delegates_to_engine() -> None:
    mod = importlib.import_module(f"atdd.tester.validators.{_SUPERSEDED[0]}")
    fn = getattr(mod, "_is_valid_train_ref", None)
    assert callable(fn), "test_urn_spec_v3 must expose _is_valid_train_ref (engine-delegating)"
    assert fn("train:artifact-identity:migrate-with-alias") is True   # typed (#1421)
    assert fn("train:0001-self-compliance-validate") is True          # legacy, still live in engine
    assert fn("not-a-train") is False
    assert fn("train:BadCaps") is False


@pytest.mark.parametrize("mod_name", ["test_typescript_test_naming", "test_typescript_test_structure"])
def test_typescript_urn_check_delegates_to_engine(mod_name: str) -> None:
    mod = importlib.import_module(f"atdd.tester.validators.{mod_name}")
    fn = getattr(mod, "_is_valid_test_urn", None)
    assert callable(fn), f"{mod_name} must expose _is_valid_test_urn (engine-delegating)"
    assert fn("test:train:0001-self-compliance-validate:E2E-001-lifecycle") is True
    assert fn("test:auth:session:M002-UNIT-003-trace-created") is True
    assert fn("acc:auth:E001-UNIT-001") is True
    assert fn("total garbage") is False


@pytest.mark.parametrize("mod_name", ["test_train_backend_e2e", "test_train_frontend_python", "test_train_frontend_e2e"])
def test_train_id_recognition_delegates_to_engine(mod_name: str) -> None:
    mod = importlib.import_module(f"atdd.tester.validators.{mod_name}")
    fn = getattr(mod, "_is_train_id", None)
    assert callable(fn), f"{mod_name} must expose _is_train_id (engine-delegating)"
    assert fn("0001-self-compliance-validate") is True
    assert fn("not_a_train_id") is False
