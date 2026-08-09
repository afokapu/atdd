"""Policy-free detection primitives for Python self-skip and failure constructs.

This module is a KERNEL: it reports *facts about source text* and makes no
decision about what they mean. It carries **no rule_id, no severity, no
disposition and no selector** — deliberately, and
``test_self_skip_kernel.py::test_kernel_exposes_no_policy`` pins that. A caller
supplies the policy: which files are in scope, which finding to report, and what
verdict a finding implies.

WHY A KERNEL, AND WHY HERE
    Two detectors matched self-skip mechanisms with two independently maintained
    copies of the same regex table:

      * core  ``src/atdd/tester/validators/test_live_smoke_execution.py``
      * this workspace's ``live_smoke_execution.py``

    The tables were identical; the *selection rules over them* were not, and had
    silently diverged (see SELECTION IS POLICY below). The duplication worth
    removing is the matcher table — the shared fact. The selection rule is policy
    and stays with each caller.

    The kernel lives in the WORKSPACE, not core: core imports no detector code,
    ``.atdd/workspaces/`` is digest-pinned installed substrate that a consumer
    repo may not have, and the sanctioned core->detector channel is the provider
    subprocess boundary, never an import. Core therefore keeps its own copy and
    is held to this table by a parity test that reads this file as text
    (``src/atdd/tester/validators/tests/test_self_skip_matcher_parity.py``), so
    the two cannot drift without a red test.

SELECTION IS POLICY — the divergence this kernel makes visible
    Given a source carrying more than one mechanism, the two callers disagree
    about which one to name, and both are defensible:

        @pytest.mark.skipif(True)      core:       "pytest.skip(...)"      (table order)
        def t():                       standalone: "@pytest.mark.skipif"   (source position)
            pytest.skip("x")

    So :func:`find_self_skips` returns **every** finding, ordered by source
    position, each carrying the index of the matcher that produced it. A caller
    selecting ``min(findings, key=lambda f: f.matcher_index)`` reproduces core's
    table-order rule; ``findings[0]`` reproduces this workspace's position rule.
    Neither is baked in.

KNOWN LIMITATION (inherited, unchanged)
    Matching is a regex over RAW source: comments and docstrings are not
    stripped, so prose containing ``pytest.skip()`` can match. The finding is
    still a true positive for "this file contains a self-skip token", but the
    reported site may point at the prose. Recorded rather than fixed — changing
    it would change both callers' behaviour, which this extraction must not do.

Pure stdlib (``ast``, ``re``). No third-party and no ``atdd.*`` imports.
"""
from __future__ import annotations

import ast
import re
from dataclasses import dataclass
from typing import Optional, Tuple

#: Self-skip mechanisms that let a test "pass" by never executing.
#:
#: Authored as ``(pattern_source, label)`` STRINGS rather than compiled objects
#: so the table is introspectable as data: the core parity test AST-parses this
#: literal without importing the module (core must not import detector code).
#: Order is significant to callers that select by table order — append only.
SELF_SKIP_MATCHERS: Tuple[Tuple[str, str], ...] = (
    (r"\bpytest\.skip\s*\(", "pytest.skip(...)"),
    (r"\bpytest\.importorskip\s*\(", "pytest.importorskip(...)"),
    (r"@\s*(?:pytest\.mark\.)?skipif\b", "@pytest.mark.skipif"),
    (r"@\s*(?:pytest\.mark\.)?skip\b", "@pytest.mark.skip"),
    (r"\bmark\.skipif?\s*\(", "pytest.mark.skip(if)(...)"),
    (r"\blive_smoke_available\s*\(", "live_smoke_available() self-skip guard"),
)

_COMPILED: Tuple[Tuple[re.Pattern, str], ...] = tuple(
    (re.compile(src), label) for src, label in SELF_SKIP_MATCHERS
)


@dataclass(frozen=True)
class SelfSkipFinding:
    """One matched self-skip site. A fact, not a verdict.

    Attributes:
        line: 1-based line of the match.
        col: 0-based column of the match.
        mechanism: Human label for the matched construct.
        matcher_index: Position in :data:`SELF_SKIP_MATCHERS` that matched, so a
            caller can reproduce a table-order selection rule.
    """

    line: int
    col: int
    mechanism: str
    matcher_index: int


@dataclass(frozen=True)
class SourceFacts:
    """Everything the kernel can say about one source text.

    Attributes:
        self_skips: Every self-skip site, ordered by (line, col).
        has_explicit_failure: True if any ``assert`` or ``raise`` is present —
            the construct that lets a function fail loudly.
        other_failure_constructs: Recognised non-``assert``/``raise`` failure
            constructs found (e.g. ``pytest.fail``, ``pytest.raises``). Reported
            because a caller treating their absence as "cannot fail" would be
            wrong; the kernel takes no position on whether they suffice.
        parseable: False when the source is not valid Python, so a caller can
            distinguish "no findings" from "could not look" and refuse rather
            than pass vacuously.
    """

    self_skips: Tuple[SelfSkipFinding, ...]
    has_explicit_failure: bool
    other_failure_constructs: Tuple[str, ...]
    parseable: bool


#: Recognised failure constructs that are neither ``assert`` nor ``raise``.
#: Reported as facts; whether they count is the caller's policy.
_OTHER_FAILURE_CALLS: Tuple[str, ...] = (
    "pytest.fail",
    "pytest.raises",
    "pytest.warns",
    "self.assertRaises",
    "unittest.TestCase.assertRaises",
)


def find_self_skips(source: str) -> Tuple[SelfSkipFinding, ...]:
    """Every self-skip site in *source*, ordered by source position.

    Returns an empty tuple when none match. Never raises: the scan is a regex
    over raw text and does not require the source to parse.
    """
    findings = []
    for index, (pattern, label) in enumerate(_COMPILED):
        for match in pattern.finditer(source):
            line = source.count("\n", 0, match.start()) + 1
            line_start = source.rfind("\n", 0, match.start()) + 1
            findings.append(
                SelfSkipFinding(
                    line=line,
                    col=match.start() - line_start,
                    mechanism=label,
                    matcher_index=index,
                )
            )
    findings.sort(key=lambda f: (f.line, f.col, f.matcher_index))
    return tuple(findings)


def first_by_matcher_order(
    findings: Tuple[SelfSkipFinding, ...],
) -> Optional[SelfSkipFinding]:
    """The finding whose matcher appears earliest in :data:`SELF_SKIP_MATCHERS`.

    Offered as a named helper because it is one of the two selection rules in
    use, not because the kernel prefers it. Ties break on source position.
    """
    if not findings:
        return None
    return min(findings, key=lambda f: (f.matcher_index, f.line, f.col))


def first_by_source_position(
    findings: Tuple[SelfSkipFinding, ...],
) -> Optional[SelfSkipFinding]:
    """The earliest finding by (line, col) — the other selection rule in use."""
    return findings[0] if findings else None


def _other_failure_constructs(tree: ast.AST) -> Tuple[str, ...]:
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted_name(node.func)
        if name and name in _OTHER_FAILURE_CALLS and name not in found:
            found.append(name)
    # ``with pytest.raises(...)`` parses as a Call too, so the walk above covers
    # it; nothing extra is needed for the context-manager form.
    return tuple(found)


def _dotted_name(node: ast.AST) -> Optional[str]:
    parts = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def analyze_source(source: str) -> SourceFacts:
    """All kernel facts about *source*, with no policy applied.

    An unparseable source yields ``parseable=False`` with the regex-based
    self-skip findings still populated (that scan does not need a parse) and the
    AST-derived fields conservatively empty/False — so a caller can tell
    "looked and found nothing" from "could not look".
    """
    skips = find_self_skips(source)
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return SourceFacts(
            self_skips=skips,
            has_explicit_failure=False,
            other_failure_constructs=(),
            parseable=False,
        )
    has_explicit = any(
        isinstance(node, (ast.Assert, ast.Raise)) for node in ast.walk(tree)
    )
    return SourceFacts(
        self_skips=skips,
        has_explicit_failure=has_explicit,
        other_failure_constructs=_other_failure_constructs(tree),
        parseable=True,
    )


def function_has_explicit_failure(source: str, func_name: str) -> Optional[bool]:
    """Whether ``func_name`` contains an ``assert``/``raise``, or None if absent.

    The function-scoped form of :attr:`SourceFacts.has_explicit_failure`. Returns
    ``None`` — never ``False`` — when the source will not parse or the function
    is not found, so "could not look" stays distinguishable from "looked and
    found none".
    """
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return any(
                isinstance(inner, (ast.Assert, ast.Raise))
                for inner in ast.walk(node)
            )
    return None


__all__ = [
    "SELF_SKIP_MATCHERS",
    "SelfSkipFinding",
    "SourceFacts",
    "analyze_source",
    "find_self_skips",
    "first_by_matcher_order",
    "first_by_source_position",
    "function_has_explicit_failure",
]
