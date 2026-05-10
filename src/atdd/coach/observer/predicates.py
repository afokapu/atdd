# URN: component:observe-and-correct:observer-runtime-and-rules:substrate_predicates:backend:domain
# Runtime: python
# Purpose: Substrate-aware observer-rule predicates for #514 — rules 10/11/12/17 per coach spec §8.3.

"""Predicates and correction-text builders for the four substrate-aware
observer rules (issue #514).

Each predicate is pure: it consumes an ``ObservedInput`` (with
``worktree_root`` and ``worktree_changes``) and returns a ``bool``. The
matching correction-text builder reproduces enough detail (rule_id,
location, expected canonical form, spec citation) for the agent to act
without re-deriving the violation context.

Rule mapping (spec §8.3 numbering → canonical id):

    10 → coach.observer.stale-suppression-detected
    11 → coach.observer.unbound-rule-id-in-validator
    12 → coach.observer.rule-id-grammar-violation
    17 → coach.observer.repo-rule-disposition-declared
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Iterable, List, Optional

import yaml


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _changed_files(ctx) -> List[Path]:
    """Return absolute paths for ``ctx.worktree_changes`` resolved against
    ``ctx.worktree_root``.

    Files that no longer exist (deletions surfaced by ``_scan_worktree``)
    are skipped — the predicates only inspect *added* / *modified*
    content, never removals.
    """
    if ctx.worktree_root is None:
        return []
    root = Path(ctx.worktree_root)
    out: List[Path] = []
    for rel in ctx.worktree_changes:
        p = root / rel
        if p.is_file():
            out.append(p)
    return out


def _rel_path(ctx, abs_path: Path) -> str:
    """Return *abs_path* relative to ``ctx.worktree_root`` as a forward-slashed string."""
    if ctx.worktree_root is None:
        return str(abs_path)
    return str(abs_path.relative_to(Path(ctx.worktree_root))).replace("\\", "/")


def _read_text(path: Path) -> Optional[str]:
    """Best-effort UTF-8 read; ``None`` when the file is unreadable."""
    if not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Rule 10 — stale-suppression-detected
# ---------------------------------------------------------------------------

# Marker pattern lifted from suppression_scanner so the predicate can run
# scoped to ``ctx.worktree_changes`` without forcing a full repo walk on
# every observer pass.
_MARKER_RE = re.compile(
    r"atdd:suppress\(([^)]+)\)(?:\s+UNTIL=(\d{4}-\d{2}-\d{2}))?",
)
_STALE_SCAN_EXTS = (".py", ".ts", ".tsx")


def _iter_stale_markers_in_file(path: Path, today):
    text = _read_text(path)
    if text is None:
        return
    for lineno, line in enumerate(text.splitlines(), start=1):
        for m in _MARKER_RE.finditer(line):
            rid = m.group(1).strip()
            until_raw = m.group(2)
            if not until_raw:
                continue
            from datetime import date as _date
            until = _date.fromisoformat(until_raw)
            if until >= today:
                continue
            yield rid, lineno, until


def stale_suppression_predicate(ctx) -> bool:
    """Return True iff at least one changed file carries a stale
    ``# atdd:suppress(<toolkit-rule-id>) [UNTIL=<past>]`` marker.

    Markers naming ``repo.*`` rule_ids are skipped per substrate v12 §2
    (repo rules are unsuppressible — firing here would invite the agent
    to "fix" a marker that was never effective)."""
    from datetime import date as _date

    today = _date.today()
    for path in _changed_files(ctx):
        if path.suffix not in _STALE_SCAN_EXTS:
            continue
        for rid, _lineno, _until in _iter_stale_markers_in_file(path, today):
            if rid.startswith("repo."):
                continue
            return True
    return False


def stale_suppression_correction(ctx, *, base_text: str) -> str:
    """Append the first matching marker's coordinates to ``base_text``.

    The base correction text is shipped in the rule YAML; this builder
    enriches it with the concrete ``{rule_id}``, ``{location}``, and
    expired ``{date}`` so the agent does not have to re-derive them."""
    from datetime import date as _date

    today = _date.today()
    for path in _changed_files(ctx):
        if path.suffix not in _STALE_SCAN_EXTS:
            continue
        for rid, lineno, until in _iter_stale_markers_in_file(path, today):
            if rid.startswith("repo."):
                continue
            location = f"{path}:{lineno}"
            return base_text.format(
                rule_id=rid,
                location=location,
                date=until.isoformat(),
            )
    return base_text


# ---------------------------------------------------------------------------
# Rule 11 — unbound-rule-id-in-validator
# ---------------------------------------------------------------------------
#
# A validator file under ``src/atdd/<archetype>/validators/`` is "unbound"
# when it emits a Violation / sets a rule_id literal at module-import
# time without a peer ``bind_rule(...)`` call also at module-import time.
# Detection is conservative source-text scanning — if the file imports
# bind_rule and uses it at top-level, the predicate considers the
# validator bound; otherwise, if it textually emits a rule_id literal,
# the predicate fires.

_VALIDATOR_PATH_RE = re.compile(
    r"(?:^|/)src/atdd/[^/]+/validators/[^/]+\.py$"
)
_RULE_ID_LITERAL_RE = re.compile(
    r"""rule_id\s*=\s*['"]([^'"]+)['"]"""
)
_BIND_RULE_CALL_RE = re.compile(r"\bbind_rule\s*\(")


def _is_validator_path(rel: str) -> bool:
    return bool(_VALIDATOR_PATH_RE.search(rel.replace("\\", "/")))


def _file_has_module_level_bind_rule(text: str) -> bool:
    """Return True iff a top-level statement in the module invokes
    ``bind_rule(...)`` — i.e. the call runs at module-import time.

    Uses an AST walk so docstrings, comments, and strings that mention
    ``bind_rule`` do not falsely satisfy the SPEC-COACH-RULEID-0007
    contract; only an actual top-level Call node counts. Indented
    occurrences (inside functions / classes) do NOT count: those fire
    only when the function runs."""
    import ast

    tree = ast.parse(text)
    for node in tree.body:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call):
                func = sub.func
                if isinstance(func, ast.Name) and func.id == "bind_rule":
                    return True
                if isinstance(func, ast.Attribute) and func.attr == "bind_rule":
                    return True
    return False


def _file_emits_rule_id_literal(text: str) -> Optional[str]:
    """Return the first ``rule_id="..."`` literal value in *text*, or
    ``None``. Uses AST so docstrings / comments don't false-positive."""
    import ast

    tree = ast.parse(text)
    for node in ast.walk(tree):
        if isinstance(node, ast.keyword) and node.arg == "rule_id":
            v = node.value
            if isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value:
                return v.value
        if isinstance(node, ast.Assign):
            for tgt in node.targets:
                if isinstance(tgt, ast.Name) and tgt.id == "RULE_ID":
                    if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                        return node.value.value
    return None


def _find_unbound_validator(ctx) -> Optional[tuple[str, str]]:
    """Return ``(rule_id, rel_path)`` for the first unbound validator
    in ``ctx.worktree_changes``, or ``None``."""
    for path in _changed_files(ctx):
        rel = _rel_path(ctx, path)
        if not _is_validator_path(rel):
            continue
        text = _read_text(path)
        if text is None:
            continue
        emitted = _file_emits_rule_id_literal(text)
        if not emitted:
            continue
        if _file_has_module_level_bind_rule(text):
            continue
        return emitted, rel
    return None


def unbound_rule_id_predicate(ctx) -> bool:
    return _find_unbound_validator(ctx) is not None


def unbound_rule_id_correction(ctx, *, base_text: str) -> str:
    hit = _find_unbound_validator(ctx)
    if hit is None:
        return base_text
    emitted, rel = hit
    return base_text.format(rule_id=emitted, location=rel)


# ---------------------------------------------------------------------------
# Rule 12 — rule-id-grammar-violation
# ---------------------------------------------------------------------------

# Canonical grammar per SPEC-COACH-RULEID-0001 (mirror of the validator).
_CANONICAL_RULE_ID_RE = re.compile(
    r"^[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*$"
)


def _iter_rule_decls(node, path_parts=()):
    """Walk a YAML doc; yield rule dicts found under any ``rules:`` key.

    Mirrors ``rule_binding._walk_rules`` but does not require the rule
    dict to have an ``id`` field — rule 12 detects the *absence* of
    canonical ids, including ones declared with non-canonical strings.
    """
    if isinstance(node, dict):
        for k, v in node.items():
            if k == "rules" and isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        yield item
            else:
                yield from _iter_rule_decls(v, path_parts + (k,))
    elif isinstance(node, list):
        for item in node:
            yield from _iter_rule_decls(item, path_parts)


def _is_convention_yaml(rel: str) -> bool:
    return rel.replace("\\", "/").endswith(".convention.yaml")


def _violating_rule_ids(text: str) -> List[str]:
    data = yaml.safe_load(text)
    out: List[str] = []
    for rule in _iter_rule_decls(data):
        rid = rule.get("id")
        if not isinstance(rid, str) or not rid:
            continue
        if _CANONICAL_RULE_ID_RE.match(rid):
            continue
        out.append(rid)
    return out


def _find_grammar_violation(ctx) -> Optional[tuple[str, str]]:
    for path in _changed_files(ctx):
        rel = _rel_path(ctx, path)
        if not _is_convention_yaml(rel):
            continue
        text = _read_text(path)
        if text is None:
            continue
        bad = _violating_rule_ids(text)
        if bad:
            return bad[0], rel
    return None


def rule_id_grammar_predicate(ctx) -> bool:
    return _find_grammar_violation(ctx) is not None


def rule_id_grammar_correction(ctx, *, base_text: str) -> str:
    hit = _find_grammar_violation(ctx)
    if hit is None:
        return base_text
    legacy_id, rel = hit
    return base_text.format(legacy_id=legacy_id, location=rel)


# ---------------------------------------------------------------------------
# Rule 17 — repo-rule-disposition-declared
# ---------------------------------------------------------------------------


def _is_plan_yaml(rel: str) -> bool:
    """Repo-rule YAML lives under ``plan/<wagon>/`` (acceptances) or
    ``plan/_trains/`` (train acceptances) or ``plan/<wagon>/features/``
    (feature.yaml::abuse_cases). Conventions under ``src/atdd/`` are
    out of scope — toolkit rules legitimately declare ``disposition``."""
    rel = rel.replace("\\", "/")
    if not rel.startswith("plan/"):
        return False
    return rel.endswith(".yaml")


def _disposition_in_plan_yaml(text: str) -> bool:
    """Return True iff the YAML declares a ``disposition:`` field
    anywhere under a top-level ``acceptances:`` list or under
    ``security.abuse_cases:``.

    The substrate v12 walker (``rule_binding._find_disposition_anywhere``)
    rejects ``disposition:`` anywhere in repo YAML — we mirror that
    breadth here so the observer matches the validator's blast radius."""
    data = yaml.safe_load(text)
    if not isinstance(data, dict):
        return False
    return _scan_for_disposition(data)


def _scan_for_disposition(node) -> bool:
    if isinstance(node, dict):
        if "disposition" in node:
            return True
        for v in node.values():
            if _scan_for_disposition(v):
                return True
    elif isinstance(node, list):
        for item in node:
            if _scan_for_disposition(item):
                return True
    return False


def _find_disposition_in_plan(ctx) -> Optional[str]:
    for path in _changed_files(ctx):
        rel = _rel_path(ctx, path)
        if not _is_plan_yaml(rel):
            continue
        text = _read_text(path)
        if text is None:
            continue
        if _disposition_in_plan_yaml(text):
            return rel
    return None


def disposition_declared_predicate(ctx) -> bool:
    return _find_disposition_in_plan(ctx) is not None


def disposition_declared_correction(ctx, *, base_text: str) -> str:
    rel = _find_disposition_in_plan(ctx)
    if rel is None:
        return base_text
    return base_text.format(location=rel)


# ---------------------------------------------------------------------------
# Public dispatch (consumed by observer._build_rule_from_yaml)
# ---------------------------------------------------------------------------


_TRIGGER_REGISTRY = {
    "stale_suppression": (stale_suppression_predicate, stale_suppression_correction),
    "unbound_rule_id_in_validator": (
        unbound_rule_id_predicate,
        unbound_rule_id_correction,
    ),
    "rule_id_grammar_violation": (
        rule_id_grammar_predicate,
        rule_id_grammar_correction,
    ),
    "repo_rule_disposition_declared": (
        disposition_declared_predicate,
        disposition_declared_correction,
    ),
}


def get_substrate_trigger(trig_type: str):
    """Return ``(predicate, correction_builder)`` for a substrate-aware
    trigger type, or ``None`` when the type is not in the registry."""
    return _TRIGGER_REGISTRY.get(trig_type)


__all__ = [
    "disposition_declared_correction",
    "disposition_declared_predicate",
    "get_substrate_trigger",
    "rule_id_grammar_correction",
    "rule_id_grammar_predicate",
    "stale_suppression_correction",
    "stale_suppression_predicate",
    "unbound_rule_id_correction",
    "unbound_rule_id_predicate",
]
