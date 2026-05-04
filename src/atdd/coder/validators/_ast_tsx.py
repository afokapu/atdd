"""
Thin wrapper around ``tree-sitter-typescript`` for TSX parsing.

Isolating the parser dependency in one module keeps the rest of the validator
suite free of tree-sitter imports and makes a future swap (e.g. to
``@swc/wasm-typescript`` via WASM bindings) a one-file change.

Decision #2 in issue #334 mandated AST parsing over regex; this module is the
substrate that enforces that decision.
"""

from __future__ import annotations

from typing import Optional


_TSX_PARSER = None


class TSXParserUnavailable(RuntimeError):
    """Raised when ``tree-sitter`` / ``tree-sitter-typescript`` are not importable."""


def _build_parser():
    """Lazy-import tree-sitter; raise ``TSXParserUnavailable`` if unavailable.

    The import is lazy so consumer repos that have not opted into
    ``no_stub_presentation`` (and therefore never reach the detection path)
    do not pay the cost of failing imports.
    """
    try:
        import tree_sitter_typescript
        from tree_sitter import Language, Parser
    except ImportError as exc:
        raise TSXParserUnavailable(
            "tree-sitter and tree-sitter-typescript are required for "
            "no_stub_presentation detection. Install with: "
            "pip install tree-sitter tree-sitter-typescript"
        ) from exc

    language = Language(tree_sitter_typescript.language_tsx())
    return Parser(language)


def get_tsx_parser():
    """Return a process-wide cached TSX parser instance."""
    global _TSX_PARSER
    if _TSX_PARSER is None:
        _TSX_PARSER = _build_parser()
    return _TSX_PARSER


def parse_tsx(source: bytes):
    """Parse TSX source bytes and return the tree-sitter ``Tree`` root node.

    Returns ``None`` if the parser is unavailable so callers can degrade
    gracefully (typical in environments without tree-sitter installed).
    """
    try:
        parser = get_tsx_parser()
    except TSXParserUnavailable:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
        return None
    return parser.parse(source)


__all__ = ["get_tsx_parser", "parse_tsx", "TSXParserUnavailable"]
