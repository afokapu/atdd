"""
Unit tests for the AST-based duplicate-code detector in
``test_quality_metrics.find_duplicate_code_blocks`` (issue #459).

Phase 2 of #459 swapped the line-based literal-match algorithm for an AST
sliding-window matcher (Option C). These four fixtures lock in the new
behavior:

  (a) ``__init__.py`` re-export idiom → 0 violations  (regression cover for
      the originally-reported false-positive shape).
  (b) Genuinely duplicated imperative code (loop body) → flagged.
  (c) Two structurally-identical functions with different identifier names →
      flagged. Locks in the rename-insensitive semantics so they aren't
      silently weakened later.
  (d) ABC port/adapter pattern → unflagged WITHOUT the old hardcoded
      ``from abc import`` / ``from dataclasses import`` exclusion (removed in
      Phase 2 — Decision row 5 of the issue body).

Reference:
  src/atdd/coder/validators/test_quality_metrics.py
  src/atdd/coder/validators/test_duplication_detector.py (helpers reused)
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from atdd.coder.validators.test_quality_metrics import (
    MIN_DUPLICATE_STATEMENTS,
    find_duplicate_code_blocks,
)


def _write(path: Path, source: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(source).lstrip(), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Fixture (a) — re-export idiom must NOT trigger
# ---------------------------------------------------------------------------
def test_reexport_init_py_does_not_flag_against_composition_module(tmp_path):
    """The canonical false-positive shape from the issue body: an ``__init__``
    that re-exports the same identifiers as a sibling ``composition`` module.
    Each file is ONE ``ImportFrom`` statement; a 5-statement window can't span
    them, so no fragment hash collides → 0 violations.
    """
    init_py = _write(
        tmp_path / "pkg" / "__init__.py",
        """
        from .submod import (
            SymbolA,
            SymbolB,
            SymbolC,
            SymbolD,
            SymbolE,
        )
        """,
    )
    composition_py = _write(
        tmp_path / "pkg" / "composition.py",
        """
        from .application import (
            SymbolA,
            SymbolB,
            SymbolC,
            SymbolD,
            SymbolE,
        )
        """,
    )

    duplicates = find_duplicate_code_blocks([init_py, composition_py])

    assert duplicates == [], (
        "AST detector flagged a re-export pair as a duplicate — the very "
        "false-positive shape #459 was filed for. "
        f"Got: {duplicates}"
    )


# ---------------------------------------------------------------------------
# Fixture (b) — real imperative duplication MUST trigger
# ---------------------------------------------------------------------------
def test_genuine_imperative_duplication_is_flagged(tmp_path):
    """Two files with the same multi-statement loop body must still be
    flagged after the algorithm switch.
    """
    body = """
    def aggregate(items):
        running_total = 0
        squared_total = 0
        counter = 0
        threshold = 100
        multiplier = 2
        ceiling = threshold * multiplier
        for entry in items:
            running_total = running_total + entry.value
            counter = counter + 1
        return (running_total, squared_total, counter, ceiling)
    """
    file_a = _write(tmp_path / "pkg" / "module_a.py", body)
    file_b = _write(tmp_path / "pkg" / "module_b.py", body)

    duplicates = find_duplicate_code_blocks([file_a, file_b])

    assert duplicates, (
        "AST detector failed to flag genuine multi-statement duplication. "
        "Real signal must survive the algorithm change."
    )
    flagged_pair = {duplicates[0][0], duplicates[0][1]}
    assert flagged_pair == {file_a, file_b}


# ---------------------------------------------------------------------------
# Fixture (c) — rename-insensitive: structurally identical, names differ
# ---------------------------------------------------------------------------
def test_rename_insensitive_duplication_is_flagged(tmp_path):
    """Two functions with identical AST structure but completely different
    identifier names. The old line-based algorithm would have missed these
    (literal-line match required identical text); the AST normalizer maps
    every Name to ``"VAR"`` and every constant to ``0``/``""``, so the two
    fragments hash equal.

    This test locks in the rename-insensitive semantic shift documented in
    the #459 body (In Scope, paragraph on the new behavior). Without it, a
    future "optimization" could silently re-narrow the rule.
    """
    file_a = _write(
        tmp_path / "alpha.py",
        """
        def transform_alpha(records):
            collected = []
            highest = 0
            offset = 0
            multiplier = 2
            ceiling = 1000
            limit = ceiling - offset
            for record in records:
                collected.append(record.value * multiplier)
            return (collected, highest, limit)
        """,
    )
    file_b = _write(
        tmp_path / "beta.py",
        """
        def process_beta(rows):
            output = []
            biggest = 0
            shift = 0
            scale = 2
            cap = 1000
            bound = cap - shift
            for row in rows:
                output.append(row.amount * scale)
            return (output, biggest, bound)
        """,
    )

    duplicates = find_duplicate_code_blocks([file_a, file_b])

    assert duplicates, (
        "Rename-insensitive duplication NOT flagged — the AST normalizer "
        "should map distinct identifier names to the same hash. If this "
        "test starts passing-as-empty, the new semantics have been silently "
        "weakened."
    )
    flagged_pair = {duplicates[0][0], duplicates[0][1]}
    assert flagged_pair == {file_a, file_b}


# ---------------------------------------------------------------------------
# Fixture (d) — ABC port/adapter pair must NOT trigger without the old hack
# ---------------------------------------------------------------------------
def test_abc_port_adapter_pattern_not_flagged_without_legacy_exclusion(tmp_path):
    """Phase 2 removed the hardcoded
    ``'from abc import' in block_text and 'from dataclasses import' in block_text``
    exclusion (Decision row 5). This fixture mirrors the port/adapter pattern
    that exclusion was protecting — two files sharing the same import preamble
    but with structurally different bodies — and proves the AST normalizer
    handles it correctly without the heuristic.

    The two files share 2 import statements but diverge in their class bodies
    (port has an abstract method; adapter is a regular concrete class), so
    no 5-statement window hashes equal across files.
    """
    port_py = _write(
        tmp_path / "ports" / "greeting_port.py",
        """
        from abc import ABC, abstractmethod
        from dataclasses import dataclass

        @dataclass
        class GreetingRequest:
            name: str

        class GreetingPort(ABC):
            @abstractmethod
            def greet(self, request: GreetingRequest) -> str:
                ...
        """,
    )
    adapter_py = _write(
        tmp_path / "adapters" / "indenting_formatter.py",
        """
        from abc import ABC, abstractmethod
        from dataclasses import dataclass

        @dataclass
        class FormatterConfig:
            indent: int

        class IndentingFormatter:
            def __init__(self, config: FormatterConfig) -> None:
                self._config = config

            def format(self, text: str) -> str:
                return " " * self._config.indent + text
        """,
    )

    duplicates = find_duplicate_code_blocks([port_py, adapter_py])

    assert duplicates == [], (
        "AST detector flagged a port/adapter pair as duplicate after the "
        "legacy ABC/dataclass exclusion was removed. Decision row 5 of "
        f"#459 says this should not regress. Got: {duplicates}"
    )


# ---------------------------------------------------------------------------
# Sanity: constant matches the calibrated value
# ---------------------------------------------------------------------------
def test_min_duplicate_statements_is_calibrated_value():
    """Phase 1 (#459) calibrated the threshold to 5. If someone changes it,
    the calibration table in docs/calibration-459-min-statements.md should
    be re-validated and updated alongside.
    """
    assert MIN_DUPLICATE_STATEMENTS == 5
