# URN: component:govern-lifecycle:enforcement-substrate:test_fix_hint_completeness:backend:domain
# Runtime: python
# Purpose: Audit every fix_hint (convention-declared or CLI-printed `Fix:`) against the C1-C4 completeness contract from rule-id.convention.yaml (issue #467).

"""Coach meta-validator: fix-hint completeness contract (issue #467).

Walks every ``*.convention.yaml`` file under the toolkit and every
``print(... Fix: ...)`` literal under ``src/atdd/**/{commands,validators}/``,
extracts the hint text, and asserts the C1-C4 contract declared in
``rule_schema.fields.fix_hint.description`` of
``src/atdd/coach/conventions/rule-id.convention.yaml``:

  * C1 — Placeholder resolution. Every ``<placeholder>`` token must be
        locally resolved (pipe-enumeration ``<a|b|c>``, function-call
        context ``f(<x>)``, quoted form ``'<x>'``) OR the hint must
        contain at least one resolver pattern line (``e.g. "..."``,
        ``(see <file>::<path>)``, ``(run <command>)``).
  * C2 — No deprecation contradiction. The first ``atdd <subcommand>``
        referenced by a hint MUST NOT be flagged deprecated by the
        ``_deprecation_warning`` registry built from ``src/atdd/cli.py``.
  * C3 — Prerequisite disclosure (heuristic; current shape: structural
        check skipped in 3.8.0; deferred to follow-up if maintenance
        friction warrants enabling it).
  * C4 — Runnable as printed. Optional sandbox-smoke; deferred.

Known-defective sites are listed under
``rule-id.convention.yaml::fix_hint_exemplars.negative`` with their
owning issue number; the validator skips those locations so the gate
becomes green automatically when the surgical fix lands and the
exemplar entry is removed.

Rule emitted: ``coach.rule-id.fix-hint-completeness``.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import pytest
import yaml

import atdd
from atdd.coach.utils.rule_binding import (
    bind_rule,
    extract_rules,
    find_convention_files,
)
from atdd.coach.validators._violation import Violation


pytestmark = [pytest.mark.coach]


_RULE = bind_rule("coach.rule-id.fix-hint-completeness")

ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
RULE_ID_CONVENTION = (
    ATDD_PKG_DIR / "coach" / "conventions" / "rule-id.convention.yaml"
)
CLI_FILE = ATDD_PKG_DIR / "cli.py"

# Python source roots that may carry print(... Fix: ...) hint literals.
_PY_HINT_ROOTS = [
    ATDD_PKG_DIR / "coach" / "commands",
    ATDD_PKG_DIR / "coach" / "validators",
    ATDD_PKG_DIR / "coder" / "commands",
    ATDD_PKG_DIR / "coder" / "validators",
    ATDD_PKG_DIR / "planner" / "commands",
    ATDD_PKG_DIR / "planner" / "validators",
    ATDD_PKG_DIR / "tester" / "commands",
    ATDD_PKG_DIR / "tester" / "validators",
]

# `Fix: <body>` literal embedded in a Python string (after f-string prefix).
_FIX_LINE_RE = re.compile(r'Fix:\s*(.+?)(?:["\'\\])', re.MULTILINE)
# More liberal capture for line-level scanning — strips the trailing quote.
_FIX_INLINE_RE = re.compile(r'Fix:\s*(?P<body>.+)$')

# `<placeholder>` token (no whitespace inside the brackets).
_PLACEHOLDER_RE = re.compile(r'<([A-Za-z_][A-Za-z0-9_:./|\- ]*?)>')

# Resolver-pattern markers.
_RESOLVER_RE = re.compile(
    r'(\(\s*see\s+[^)]+::[^)]+\))|(\(\s*run\s+[^)]+\))|(e\.g\.\s*["\'`])'
)

# Deprecation-registry parse — `_deprecation_warning("<old>", "<new>")`.
_DEPRECATION_CALL_RE = re.compile(
    r'_deprecation_warning\(\s*'
    r'["\'](?P<old>[^"\']+)["\']\s*,\s*'
    r'["\'](?P<new>[^"\']+)["\']'
)

# Negative-exemplar block — file:start-end form.
_LINE_RANGE_RE = re.compile(r'(?P<path>[^:]+):(?P<start>\d+)-(?P<end>\d+)')
_LINE_SINGLE_RE = re.compile(r'(?P<path>[^:]+):(?P<start>\d+)$')


# ---------------------------------------------------------------------------
# Hint extraction
# ---------------------------------------------------------------------------
class Hint:
    """A single fix-hint instance with its source location."""

    __slots__ = ("source", "rel_path", "line", "text", "kind")

    def __init__(self, source: Path, rel_path: str, line: int, text: str, kind: str):
        self.source = source
        self.rel_path = rel_path
        self.line = line
        self.text = text
        self.kind = kind  # "yaml" or "py"


def _relpath(p: Path) -> str:
    try:
        return str(p.resolve().relative_to(ATDD_PKG_DIR.parent.resolve()))
    except ValueError:
        return str(p)


def _yaml_line_for_field(file_path: Path, field_value: str) -> int:
    """Best-effort line number for a fix_hint value (for reporting)."""
    if not field_value:
        return 1
    needle = field_value.splitlines()[0].strip() if field_value.strip() else ""
    if not needle:
        return 1
    try:
        for idx, raw in enumerate(file_path.read_text(encoding="utf-8").splitlines(), 1):
            if needle and needle in raw:
                return idx
    except OSError:
        pass
    return 1


def collect_yaml_hints() -> List[Hint]:
    """Extract every ``fix_hint:`` value from every convention YAML."""
    out: List[Hint] = []
    for conv in find_convention_files():
        for (file_path, _yaml_path, rule) in extract_rules(conv):
            text = rule.get("fix_hint")
            if not isinstance(text, str) or not text.strip():
                continue
            lineno = _yaml_line_for_field(file_path, text)
            out.append(
                Hint(
                    source=file_path,
                    rel_path=_relpath(file_path),
                    line=lineno,
                    text=text,
                    kind="yaml",
                )
            )
    return out


_HINT_BLOCK_LOOKAHEAD = 6


def _is_string_continuation(line: str) -> bool:
    """A line that continues a string-literal hint block.

    Heuristic: leading whitespace then ``"``, ``'``, ``f"``, or ``f'``.
    Stops at lines that start a new statement, close the call, or
    introduce a separator like ``Bypass:`` (handled by caller).
    """
    s = line.lstrip()
    return s.startswith(('f"', "f'", '"', "'"))


def collect_py_hints() -> List[Hint]:
    """Extract every ``Fix: …`` literal under the toolkit.

    A hint is the ``Fix:`` body PLUS up to ``_HINT_BLOCK_LOOKAHEAD``
    subsequent string-continuation lines (so resolver-pattern lines like
    ``(e.g. "...")`` placed on the next f-string fragment are picked up).
    """
    out: List[Hint] = []
    for root in _PY_HINT_ROOTS:
        if not root.is_dir():
            continue
        for py in root.rglob("*.py"):
            if "__pycache__" in py.parts or "fixtures" in py.parts:
                continue
            try:
                source = py.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            lines = source.splitlines()
            for idx, raw in enumerate(lines):
                lineno = idx + 1
                if "Fix:" not in raw:
                    continue
                if (
                    "print" not in raw
                    and "lines.append" not in raw
                    and 'f"' not in raw
                    and "f'" not in raw
                ):
                    continue
                m = _FIX_INLINE_RE.search(raw)
                if not m:
                    continue
                body_parts: List[str] = [m.group("body").rstrip().rstrip(')\'"` ').rstrip()]
                # Pull in continuation string fragments to capture resolver
                # patterns split across f-string concatenation.
                for j in range(idx + 1, min(idx + 1 + _HINT_BLOCK_LOOKAHEAD, len(lines))):
                    nxt = lines[j]
                    if "Fix:" in nxt or "Bypass:" in nxt:
                        break
                    if not _is_string_continuation(nxt):
                        break
                    body_parts.append(nxt.strip().strip(')\'"` ').strip())
                body = "\n".join(p for p in body_parts if p)
                if not body:
                    continue
                out.append(
                    Hint(
                        source=py,
                        rel_path=_relpath(py),
                        line=lineno,
                        text=body,
                        kind="py",
                    )
                )
    return out


# ---------------------------------------------------------------------------
# Deprecation registry (parsed from cli.py _deprecation_warning callsites)
# ---------------------------------------------------------------------------
def build_deprecation_registry(cli_source: Optional[str] = None) -> dict:
    """Map ``"atdd <head>"`` → canonical replacement string.

    Reads ``_deprecation_warning("<old>", "<new>")`` callsites from
    ``src/atdd/cli.py``.  The "head" is the first two whitespace-separated
    tokens of the deprecated form (e.g. ``"atdd update"``); the validator
    matches Fix:-hint commands by head so flag/arg drift doesn't matter.
    """
    if cli_source is None:
        try:
            cli_source = CLI_FILE.read_text(encoding="utf-8")
        except OSError:
            return {}
    out: dict = {}
    for m in _DEPRECATION_CALL_RE.finditer(cli_source):
        old = m.group("old").strip()
        new = m.group("new").strip()
        head = " ".join(old.split()[:2])
        if head and head not in out:
            out[head] = new
    return out


# ---------------------------------------------------------------------------
# Negative-exemplar allowlist (consumed from rule-id.convention.yaml)
# ---------------------------------------------------------------------------
def load_negative_exemplars(
    convention_path: Path = RULE_ID_CONVENTION,
) -> List[Tuple[str, int, int, int]]:
    """Return ``(rel_path, start_line, end_line, owner_issue)`` tuples.

    Sites listed under ``fix_hint_exemplars.negative`` are skipped by the
    validator — they are known-defective and owned by another issue.
    """
    out: List[Tuple[str, int, int, int]] = []
    try:
        data = yaml.safe_load(convention_path.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return out
    block = (data.get("fix_hint_exemplars") or {}).get("negative") or []
    for entry in block:
        if not isinstance(entry, dict):
            continue
        src = entry.get("source", "")
        owner = entry.get("owner_issue") or 0
        m = _LINE_RANGE_RE.match(src) or _LINE_SINGLE_RE.match(src)
        if not m:
            continue
        path = m.group("path").strip()
        start = int(m.group("start"))
        end = int(m.group("end")) if "end" in m.groupdict() and m.group("end") else start
        out.append((path, start, end, int(owner) if owner else 0))
    return out


def _is_exempted(hint: Hint, exemptions: Sequence[Tuple[str, int, int, int]]) -> Optional[int]:
    for path, start, end, owner in exemptions:
        if hint.rel_path.endswith(path) or path.endswith(hint.rel_path):
            if start <= hint.line <= end:
                return owner
    return None


# ---------------------------------------------------------------------------
# Contract clauses
# ---------------------------------------------------------------------------
_RESOLVING_PREV_CHARS = set(":=/([<'\"`-*")  # ``-`` / ``*`` cover YAML/markdown bullets
_RESOLVING_NEXT_CHARS = set("/:.")          # path / qualified-name continuation


def _placeholder_is_locally_resolved(text: str, match: re.Match) -> bool:
    """A placeholder is locally resolved if it sits in any of:

    * a pipe-enumeration ``<a|b|c>`` (own value space),
    * a schema/template / function / quoted / bullet context — the
      previous non-whitespace character before the ``<`` is one of
      ``: = / ( [ < ' " ``` `` - * `` (covers ``key: <value>``,
      ``--flag=<value>``, ``f(<x>)``, ``"<x>"``, ``- <bullet>``),
    * a path / qualified-name continuation — the immediate character
      after the ``>`` is one of ``/ : .`` (covers ``<repo>/.atdd``,
      ``<name>.py``, ``<scope>:<value>``).
    """
    body = match.group(1)
    if "|" in body:
        return True
    start = match.start()
    end = match.end()
    if end < len(text) and text[end] in _RESOLVING_NEXT_CHARS:
        return True
    i = start - 1
    while i >= 0 and text[i] in " \t":
        i -= 1
    if i < 0:
        return False
    return text[i] in _RESOLVING_PREV_CHARS


def audit_c1_placeholder_resolution(text: str) -> List[str]:
    """Return a list of unresolved ``<placeholder>`` tokens."""
    placeholders = list(_PLACEHOLDER_RE.finditer(text))
    if not placeholders:
        return []
    has_resolver = bool(_RESOLVER_RE.search(text))
    unresolved: List[str] = []
    for m in placeholders:
        if has_resolver:
            continue
        if _placeholder_is_locally_resolved(text, m):
            continue
        unresolved.append(m.group(1))
    return unresolved


def audit_c2_no_deprecation_contradiction(
    text: str, registry: dict
) -> Optional[Tuple[str, str]]:
    """Return ``(deprecated_head, canonical_replacement)`` or None."""
    # Look for an `atdd <sub>` head literally appearing in the hint.
    m = re.search(r'\batdd\s+([a-z][a-z0-9-]*)', text)
    if not m:
        return None
    head = f"atdd {m.group(1)}"
    if head in registry:
        return (head, registry[head])
    return None


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------
def scan_hints() -> List[Violation]:
    """Audit every discovered hint and emit Violations for failures."""
    registry = build_deprecation_registry()
    exemptions = load_negative_exemplars()
    hints: List[Hint] = []
    hints.extend(collect_yaml_hints())
    hints.extend(collect_py_hints())

    violations: List[Violation] = []
    for hint in hints:
        if _is_exempted(hint, exemptions):
            continue

        unresolved = audit_c1_placeholder_resolution(hint.text)
        if unresolved:
            tokens = ", ".join(f"<{t}>" for t in unresolved[:5])
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"{hint.rel_path}:{hint.line}",
                    detail=(
                        f"C1 placeholder-resolution: unresolved placeholder(s) "
                        f"{tokens} in fix_hint — add a sibling resolver line "
                        f"(see <file>::<path>) / (run <command>) / e.g. \"<concrete>\"."
                    ),
                    fix_hint_ref=_RULE.fix_hint_ref,
                )
            )

        c2 = audit_c2_no_deprecation_contradiction(hint.text, registry)
        if c2 is not None:
            head, canonical = c2
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"{hint.rel_path}:{hint.line}",
                    detail=(
                        f"C2 deprecation-contradiction: hint recommends "
                        f"deprecated CLI form {head!r}; substitute the canonical "
                        f"replacement {canonical!r} (registered via "
                        f"_deprecation_warning in src/atdd/cli.py)."
                    ),
                    fix_hint_ref=_RULE.fix_hint_ref,
                )
            )

    return violations


# ===========================================================================
# Test
# ===========================================================================
@pytest.mark.coach
def test_every_fix_hint_satisfies_completeness_contract():
    """Every fix_hint in convention YAMLs and CLI ``Fix:`` literals must
    satisfy clauses C1-C2 of the contract declared in
    ``rule-id.convention.yaml::rule_schema.fields.fix_hint`` (#467).

    Sites pinned under ``fix_hint_exemplars.negative`` are exempted as
    known-defective fixtures (each carries an ``owner_issue``).  The gate
    becomes green automatically when the owning issue lands and the
    exemplar entry is removed.
    """
    violations = scan_hints()
    if not violations:
        return
    formatted = "\n".join(f"  - {v}" for v in violations)
    pytest.fail(
        f"\nFix-hint completeness contract violated by "
        f"{len(violations)} hint(s):\n\n{formatted}\n\n"
        "Repair per rule-id.convention.yaml::rule_schema.fields.fix_hint "
        "(clauses C1-C4). See coach.rule-id.fix-hint-completeness.fix_hint."
    )


__all__ = [
    "Hint",
    "audit_c1_placeholder_resolution",
    "audit_c2_no_deprecation_contradiction",
    "build_deprecation_registry",
    "collect_py_hints",
    "collect_yaml_hints",
    "load_negative_exemplars",
    "scan_hints",
    "test_every_fix_hint_satisfies_completeness_contract",
]
