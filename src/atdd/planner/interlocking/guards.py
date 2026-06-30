# URN: component:plan:train-interlocking:Guards:backend:domain
# Runtime: python
# Purpose: Declarative, side-effect-free guard grammar (parse + evaluate, NO raw eval).
"""Guard expression grammar for interlocking routes (#1248).

Guards are declarative and side-effect-free. They are tokenized and parsed into a
small immutable AST, then evaluated against a read-only context mapping. There is
**no** path to Python ``eval``/``exec``, no imports, no IO, no mutation, and no
function calls other than the single allowed built-in ``exists(field)``.

Grammar (lowest precedence first)::

    or_expr   := and_expr ("or" and_expr)*
    and_expr  := not_expr ("and" not_expr)*
    not_expr  := "not" not_expr | comparison
    comparison:= primary ( CMP primary | "in" list )?
    primary   := "(" or_expr ")" | "exists" "(" field ")" | literal | field
    CMP       := "==" | "!=" | "<" | "<=" | ">" | ">="

Allowed inputs are request/action inputs, an explicit state snapshot, and
completed TrainResult facts surfaced at declared route boundaries — all flattened
into the evaluation context by the caller.
"""
from __future__ import annotations

import logging
import re
from typing import Any, List, Mapping, Tuple

logger = logging.getLogger(__name__)

__all__ = ["GuardSyntaxError", "parse_guard", "evaluate_guard"]


class GuardSyntaxError(ValueError):
    """Raised when a guard expression is malformed or uses a forbidden construct."""


# --- sentinel for absent fields (fail-closed, never raises) -------------------
class _Missing:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __bool__(self) -> bool:
        return False

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<missing>"


_MISSING = _Missing()

_KEYWORDS = {"and", "or", "not", "in", "exists", "true", "false", "null"}

_TOKEN_RE = re.compile(
    r"""
      (?P<WS>\s+)
    | (?P<NUMBER>\d+\.\d+|\d+)
    | (?P<STRING>'[^']*'|"[^"]*")
    | (?P<CMP>==|!=|<=|>=|<|>)
    | (?P<LPAREN>\()
    | (?P<RPAREN>\))
    | (?P<LBRACK>\[)
    | (?P<RBRACK>\])
    | (?P<COMMA>,)
    | (?P<IDENT>[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)
    """,
    re.VERBOSE,
)


def _tokenize(expr: str) -> List[Tuple[str, str]]:
    tokens: List[Tuple[str, str]] = []
    pos = 0
    n = len(expr)
    while pos < n:
        m = _TOKEN_RE.match(expr, pos)
        if not m:
            raise GuardSyntaxError(
                f"unexpected character {expr[pos]!r} at position {pos} in guard {expr!r}"
            )
        kind = m.lastgroup
        text = m.group()
        pos = m.end()
        if kind == "WS":
            continue
        tokens.append((kind, text))
    return tokens


# AST node tuples:
#   ("lit", value) | ("field", name) | ("exists", name) | ("list", [values])
#   ("not", node) | ("and", l, r) | ("or", l, r)
#   ("cmp", op, l, r) | ("in", l, listnode)


class _Parser:
    def __init__(self, tokens: List[Tuple[str, str]], expr: str):
        self._tokens = tokens
        self._expr = expr
        self._i = 0

    def _peek(self) -> Tuple[str, str] | None:
        return self._tokens[self._i] if self._i < len(self._tokens) else None

    def _next(self) -> Tuple[str, str]:
        if self._i >= len(self._tokens):
            raise GuardSyntaxError(f"unexpected end of guard {self._expr!r}")
        tok = self._tokens[self._i]
        self._i += 1
        return tok

    def _is_keyword(self, kw: str) -> bool:
        tok = self._peek()
        return tok is not None and tok[0] == "IDENT" and tok[1] == kw

    def parse(self):
        node = self._parse_or()
        if self._peek() is not None:
            raise GuardSyntaxError(
                f"trailing tokens after expression in guard {self._expr!r}"
            )
        return node

    def _parse_or(self):
        node = self._parse_and()
        while self._is_keyword("or"):
            self._next()
            node = ("or", node, self._parse_and())
        return node

    def _parse_and(self):
        node = self._parse_not()
        while self._is_keyword("and"):
            self._next()
            node = ("and", node, self._parse_not())
        return node

    def _parse_not(self):
        if self._is_keyword("not"):
            self._next()
            return ("not", self._parse_not())
        return self._parse_comparison()

    def _parse_comparison(self):
        left = self._parse_primary()
        tok = self._peek()
        if tok is not None and tok[0] == "CMP":
            op = self._next()[1]
            right = self._parse_primary()
            return ("cmp", op, left, right)
        if self._is_keyword("in"):
            self._next()
            return ("in", left, self._parse_list())
        return left

    def _parse_list(self):
        tok = self._next()
        if tok[0] != "LBRACK":
            raise GuardSyntaxError(f"expected '[' after 'in' in guard {self._expr!r}")
        values: List[Any] = []
        if self._peek() is not None and self._peek()[0] == "RBRACK":
            self._next()
            return ("list", values)
        while True:
            values.append(self._parse_literal_value())
            tok = self._next()
            if tok[0] == "RBRACK":
                break
            if tok[0] != "COMMA":
                raise GuardSyntaxError(
                    f"expected ',' or ']' in list literal in guard {self._expr!r}"
                )
        return ("list", values)

    def _parse_literal_value(self) -> Any:
        tok = self._next()
        if tok[0] == "NUMBER":
            return float(tok[1]) if "." in tok[1] else int(tok[1])
        if tok[0] == "STRING":
            return tok[1][1:-1]
        if tok[0] == "IDENT" and tok[1] in ("true", "false", "null"):
            return {"true": True, "false": False, "null": None}[tok[1]]
        raise GuardSyntaxError(
            f"expected a literal value, got {tok[1]!r} in guard {self._expr!r}"
        )

    def _parse_primary(self):
        tok = self._peek()
        if tok is None:
            raise GuardSyntaxError(f"unexpected end of guard {self._expr!r}")

        if tok[0] == "LPAREN":
            self._next()
            node = self._parse_or()
            close = self._next()
            if close[0] != "RPAREN":
                raise GuardSyntaxError(f"unbalanced parentheses in guard {self._expr!r}")
            return node

        if tok[0] == "NUMBER":
            self._next()
            return ("lit", float(tok[1]) if "." in tok[1] else int(tok[1]))

        if tok[0] == "STRING":
            self._next()
            return ("lit", tok[1][1:-1])

        if tok[0] == "IDENT":
            name = tok[1]
            if name in ("true", "false", "null"):
                self._next()
                return ("lit", {"true": True, "false": False, "null": None}[name])
            if name == "exists":
                self._next()
                if self._peek() is None or self._peek()[0] != "LPAREN":
                    raise GuardSyntaxError(
                        f"exists must be called as exists(field) in guard {self._expr!r}"
                    )
                self._next()  # (
                fld = self._next()
                if fld[0] != "IDENT" or fld[1] in _KEYWORDS:
                    raise GuardSyntaxError(
                        f"exists() requires a field name in guard {self._expr!r}"
                    )
                close = self._next()
                if close[0] != "RPAREN":
                    raise GuardSyntaxError(
                        f"unbalanced parentheses in exists() in guard {self._expr!r}"
                    )
                return ("exists", fld[1])
            if name in _KEYWORDS:
                raise GuardSyntaxError(
                    f"unexpected keyword {name!r} in guard {self._expr!r}"
                )
            # plain field reference — must NOT be a function call
            self._next()
            nxt = self._peek()
            if nxt is not None and nxt[0] == "LPAREN":
                raise GuardSyntaxError(
                    f"function calls are forbidden (only exists() is allowed): "
                    f"{name!r} in guard {self._expr!r}"
                )
            return ("field", name)

        raise GuardSyntaxError(f"unexpected token {tok[1]!r} in guard {self._expr!r}")


def parse_guard(expression: str):
    """Parse a guard expression into an immutable AST. Raises GuardSyntaxError."""
    if not isinstance(expression, str) or not expression.strip():
        raise GuardSyntaxError("guard expression must be a non-empty string")
    return _Parser(_tokenize(expression), expression).parse()


def _resolve(name: str, ctx: Mapping[str, Any]) -> Any:
    cur: Any = ctx
    for part in name.split("."):
        if isinstance(cur, Mapping) and part in cur:
            cur = cur[part]
        else:
            return _MISSING
    return cur


def _compare(op: str, left: Any, right: Any) -> bool:
    if left is _MISSING or right is _MISSING:
        if op == "==":
            return left is right
        if op == "!=":
            return left is not right
        return False  # ordering against a missing field is a non-match, never an error
    if op == "==":
        return bool(left == right)
    if op == "!=":
        return bool(left != right)
    try:
        if op == "<":
            return bool(left < right)
        if op == "<=":
            return bool(left <= right)
        if op == ">":
            return bool(left > right)
        if op == ">=":
            return bool(left >= right)
    except TypeError:
        # Ordering across incomparable types (e.g. number vs string) is a
        # deliberate non-match, not a crash — but record it so the swallow is
        # observable rather than silent.
        logger.debug(
            "guard ordering comparison on incomparable types treated as non-match",
            extra={
                "op": op,
                "left_type": type(left).__name__,
                "right_type": type(right).__name__,
            },
        )
        return False
    raise GuardSyntaxError(f"unknown comparison operator {op!r}")  # pragma: no cover


def _eval(node, ctx: Mapping[str, Any]) -> Any:
    tag = node[0]
    if tag == "lit":
        return node[1]
    if tag == "field":
        return _resolve(node[1], ctx)
    if tag == "exists":
        return _resolve(node[1], ctx) is not _MISSING
    if tag == "list":
        return list(node[1])
    if tag == "not":
        return not bool(_eval(node[1], ctx))
    if tag == "and":
        return bool(_eval(node[1], ctx)) and bool(_eval(node[2], ctx))
    if tag == "or":
        return bool(_eval(node[1], ctx)) or bool(_eval(node[2], ctx))
    if tag == "cmp":
        return _compare(node[1], _eval(node[2], ctx), _eval(node[3], ctx))
    if tag == "in":
        left = _eval(node[1], ctx)
        if left is _MISSING:
            return False
        return left in _eval(node[2], ctx)
    raise GuardSyntaxError(f"unknown AST node {tag!r}")  # pragma: no cover


def evaluate_guard(ast, context: Mapping[str, Any]) -> bool:
    """Evaluate a parsed guard AST against a read-only context mapping.

    Always returns a plain ``bool``. Absent fields are treated as non-matches
    (fail-closed) rather than raising, so route resolution stays deterministic.
    """
    return bool(_eval(ast, context or {}))
