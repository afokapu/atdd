# URN: test:govern-lifecycle:operator-approval-token-gate:C010-INTEGRATION-002-guards-are-not-stubs-under-fault-injection
# Acceptance: acc:govern-lifecycle:C010-INTEGRATION-002-guards-are-not-stubs-under-fault-injection
# WMBT: wmbt:govern-lifecycle:C010
# Phase: GREEN
# Layer: integration
# Assertion: behavioral
"""C010-INTEGRATION-002 — the branch and expiry guards are load-bearing.

A gate that cannot fail is a stub. Each guard is removed IN ISOLATION from a
COPY of the approval module (the real tree is never mutated), the mutated copy
is imported, and the corresponding contract is shown to break. With no fault
injected, both contracts hold — establishing the injected fault as the sole
cause of each failure.

Regex/string fault injection FAILS OPEN: a non-matching anchor silently mutates
nothing, and a no-op edit then reads as "guard removed, suite stayed green".
Every injection here therefore asserts (a) the anchor matched EXACTLY ONCE and
(b) the mutated source still parses, so a syntax error cannot masquerade as a
failing guard either.
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]

_KEY = "operator-secret-key"
_ISSUE, _FROM, _TO = 1525, "PLANNED", "RED"

_MODULE = Path(__file__).resolve().parents[1] / "approval.py"

# The exact guards under test. Removing each must break its contract.
_BRANCH_GUARD = '    if branch:\n        scope += f":branch={branch}"\n'
_EXPIRY_GUARD = "        if now_dt > expiry_dt:\n            return False\n"


def _load_variant(source: str, tmp_path: Path, name: str):
    """Import ``source`` as a standalone module from a temp path."""
    path = tmp_path / f"{name}.py"
    path.write_text(source)
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _inject(source: str, anchor: str, replacement: str) -> str:
    """Remove one guard, proving the edit actually landed and still parses."""
    matched = source.count(anchor)
    assert matched == 1, (
        f"fault injection anchor matched {matched} times, expected EXACTLY 1 — "
        "a non-matching anchor mutates nothing and would let a no-op edit read "
        "as a removed guard"
    )
    mutated = source.replace(anchor, replacement)
    assert mutated != source, "injection produced an identical source (no-op edit)"
    ast.parse(mutated)  # a SyntaxError here would fail the test for the WRONG reason
    return mutated


def _branch_contract_holds(mod) -> bool:
    """A token signed for feat/alpha verifies there and is rejected on feat/beta."""
    token = mod.build_token(
        _ISSUE, _FROM, _TO,
        approved_by="operator", approved_at="2026-07-20T00:00:00Z",
        branch="feat/alpha", key=_KEY,
    )
    same = mod.verify_token(token, _ISSUE, _FROM, _TO, branch="feat/alpha", key=_KEY)
    other = mod.verify_token(token, _ISSUE, _FROM, _TO, branch="feat/beta", key=_KEY)
    return same is True and other is False


def _expiry_contract_holds(mod) -> bool:
    """A token verifies before its expiry and is rejected after it."""
    token = mod.build_token(
        _ISSUE, _FROM, _TO,
        approved_by="operator", approved_at="2026-07-20T00:00:00Z",
        branch="feat/alpha", expires_at="2026-07-20T00:05:00Z", key=_KEY,
    )
    before = mod.verify_token(
        token, _ISSUE, _FROM, _TO,
        branch="feat/alpha", now="2026-07-20T00:04:00Z", key=_KEY,
    )
    after = mod.verify_token(
        token, _ISSUE, _FROM, _TO,
        branch="feat/alpha", now="2026-07-20T00:06:00Z", key=_KEY,
    )
    return before is True and after is False


def test_unmutated_module_satisfies_both_contracts(tmp_path: Path):
    """Baseline: with no fault injected both guards hold, so any failure below is
    attributable to the injected fault alone."""
    pristine = _load_variant(_MODULE.read_text(), tmp_path, "approval_pristine")
    assert _branch_contract_holds(pristine)
    assert _expiry_contract_holds(pristine)


def test_removing_the_branch_binding_breaks_the_branch_contract(tmp_path: Path):
    """Drop the branch from the signed scope — a token must then verify on ANY
    branch, i.e. the replay-across-branch defect returns."""
    mutated = _inject(_MODULE.read_text(), _BRANCH_GUARD, "")
    mod = _load_variant(mutated, tmp_path, "approval_no_branch")

    assert not _branch_contract_holds(mod), (
        "removing the branch binding left the branch contract satisfied — "
        "the guard is a stub that cannot fail"
    )
    # Precisely: the token now verifies on a branch it was never signed for.
    token = mod.build_token(
        _ISSUE, _FROM, _TO,
        approved_by="operator", approved_at="2026-07-20T00:00:00Z",
        branch="feat/alpha", key=_KEY,
    )
    assert mod.verify_token(token, _ISSUE, _FROM, _TO, branch="feat/beta", key=_KEY) is True
    # The expiry guard is untouched by this fault (faults are isolated).
    assert _expiry_contract_holds(mod)


def test_removing_the_expiry_comparison_breaks_the_expiry_contract(tmp_path: Path):
    """Drop the now>expiry comparison — an expired token must then verify, i.e.
    the token is eternal again."""
    mutated = _inject(_MODULE.read_text(), _EXPIRY_GUARD, "")
    mod = _load_variant(mutated, tmp_path, "approval_no_expiry")

    assert not _expiry_contract_holds(mod), (
        "removing the expiry comparison left the expiry contract satisfied — "
        "the guard is a stub that cannot fail"
    )
    # Precisely: a token presented after its expiry now verifies.
    token = mod.build_token(
        _ISSUE, _FROM, _TO,
        approved_by="operator", approved_at="2026-07-20T00:00:00Z",
        branch="feat/alpha", expires_at="2026-07-20T00:05:00Z", key=_KEY,
    )
    assert mod.verify_token(
        token, _ISSUE, _FROM, _TO,
        branch="feat/alpha", now="2026-07-20T00:06:00Z", key=_KEY,
    ) is True
    # The branch guard is untouched by this fault (faults are isolated).
    assert _branch_contract_holds(mod)
