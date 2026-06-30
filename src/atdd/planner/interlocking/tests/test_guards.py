"""Guard grammar tests: declarative, side-effect-free, no raw eval (#1248)."""
from __future__ import annotations

import pytest

from atdd.planner.interlocking import GuardSyntaxError, evaluate_guard, parse_guard


@pytest.mark.parametrize(
    "expr,ctx,expected",
    [
        ("all_players_voted == true", {"all_players_voted": True}, True),
        ("all_players_voted == true", {"all_players_voted": False}, False),
        ("unresolved_count <= 7", {"unresolved_count": 7}, True),
        ("unresolved_count <= 7", {"unresolved_count": 8}, False),
        ("score > 3 and score < 10", {"score": 5}, True),
        ("score > 3 and score < 10", {"score": 11}, False),
        ("a == 1 or b == 2", {"a": 0, "b": 2}, True),
        ("not flag", {"flag": False}, True),
        ("not flag", {"flag": True}, False),
        ("status != 'open'", {"status": "closed"}, True),
        ("phase in ['red', 'green']", {"phase": "green"}, True),
        ("phase in ['red', 'green']", {"phase": "smoke"}, False),
        ("exists(winner)", {"winner": "blitz"}, True),
        ("exists(winner)", {}, False),
        ("exists(winner) and winner == 'blitz'", {"winner": "blitz"}, True),
    ],
)
def test_guard_evaluates(expr, ctx, expected):
    assert evaluate_guard(parse_guard(expr), ctx) is expected


def test_dotted_field_resolves_nested_state():
    ast = parse_guard("result.status == 'success'")
    assert evaluate_guard(ast, {"result": {"status": "success"}}) is True
    assert evaluate_guard(ast, {"result": {"status": "failure"}}) is False


@pytest.mark.parametrize(
    "expr",
    [
        "__import__('os').system('rm -rf /')",
        "open('/etc/passwd')",
        "os.system('x')",
        "len(items) > 0",          # function calls (except exists) forbidden
        "1 +",                     # incomplete
        "a == == b",               # malformed
        "a & b",                   # unsupported operator
        "a; b",                    # statement separator
        "lambda: 1",               # lambda forbidden
    ],
)
def test_forbidden_or_malformed_expressions_raise(expr):
    with pytest.raises(GuardSyntaxError):
        parse_guard(expr)


def test_evaluation_never_uses_python_eval(monkeypatch):
    """Hard guarantee: guard evaluation must not route through builtins.eval."""
    import builtins

    def _boom(*_a, **_k):  # pragma: no cover - only fires on violation
        raise AssertionError("raw eval() must never be called by guard evaluation")

    monkeypatch.setattr(builtins, "eval", _boom)
    ast = parse_guard("all_players_voted == true and unresolved_count <= 7")
    assert evaluate_guard(ast, {"all_players_voted": True, "unresolved_count": 3}) is True


def test_missing_field_in_comparison_is_falsey_not_error():
    # A guard that references an absent field resolves to a non-match, not a crash
    # (fail-closed route resolution depends on this being deterministic).
    ast = parse_guard("timer_expired == true")
    assert evaluate_guard(ast, {}) is False
