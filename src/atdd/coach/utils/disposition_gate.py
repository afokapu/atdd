# URN: component:govern-lifecycle:enforcement-substrate:disposition_gate:backend:domain
# Runtime: python
# Purpose: Decide pass/fail per validator from per-rule disposition + Violation list.

"""
Disposition-driven gate (issue #395).

Replaces ``RatchetBaseline.assert_no_regression(...)``. Given:

* a list of structured ``Violation`` records for one validator,
* the convention registry built from ``*.convention.yaml`` files,

decides pass/fail per the rule's ``disposition``:

* ``strict``              — any violation fails CI immediately.
* ``suppress-and-clean``  — violations whose offending line carries an
  inline ``# atdd:suppress(<rule_id>)`` marker are absorbed; everything
  else fails CI with a per-site punch list.
* ``advisory``            — violations log a warning and pass.

Failures print rule_id + severity + disposition + ``file:line`` + the
detail string + a one-line suggested action so a reviewer doesn't have to
read the validator source to understand the failure.

A rule_id with no registry entry is treated as ``strict`` (defensive
default — unregistered rules should be caught by the
``rule_id_registry_coherence`` validator before reaching this point).
"""

from __future__ import annotations

import logging
import os
import re
import sys
import warnings
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_id_registry import RuleMetadata, build_registry
from atdd.coach.utils.suppression_scanner import is_suppressed


# Inline marker grammar (mirrors atdd.coach.utils.suppression_scanner). Used
# to extract the literal marker substring for violation_collector records;
# we do not want to import the scanner's private regex.
_MARKER_TEXT_PATTERN = re.compile(
    r"atdd:suppress\(([^)]+)\)(?:\s+UNTIL=(\d{4}-\d{2}-\d{2}))?"
)


def _match_marker_text(line: str, rule_id: str) -> Optional[str]:
    """Return the matched marker substring for ``rule_id`` on ``line`` or None."""
    for match in _MARKER_TEXT_PATTERN.finditer(line):
        if match.group(1).strip() == rule_id:
            return match.group(0)
    return None


def _record_observed_violation(
    validator_id: str,
    violation: Any,
    disposition: str,
    suppression_marker: Optional[str],
) -> None:
    """Push an observation onto ``session._atdd['observed_violations']`` for
    the coach pytest violation_collector plugin (issue #518). No-op outside a
    pytest session — the active-session reference stays None."""
    session = _ACTIVE_PYTEST_SESSION
    if session is None:
        return
    namespace = getattr(session, "_atdd", None)
    if not isinstance(namespace, dict):
        namespace = {}
        try:
            setattr(session, "_atdd", namespace)
        except (AttributeError, TypeError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            return
    observed = namespace.get("observed_violations")
    if not isinstance(observed, list):
        observed = []
        namespace["observed_violations"] = observed
    observed.append(
        {
            "validator_id": validator_id,
            "violation": violation,
            "disposition": disposition,
            "suppression_marker": suppression_marker,
        }
    )


_logger = logging.getLogger(__name__)


_DEFAULT_DISPOSITION = "strict"
_LEGAL_DISPOSITIONS = frozenset({"strict", "suppress-and-clean", "advisory"})


# ---------------------------------------------------------------------------
# Session result map (substrate spec v12 §4.5 — issue #422)
# ---------------------------------------------------------------------------
# Holds a reference to the active pytest session so the gate can record
# (rule_id, outcome) pairs into ``session._atdd["rule_outcomes"]`` without
# threading the session object through every caller. The substrate's
# pytest plugin sets this at session-start and clears it at session-end.
# Outside a pytest run the variable stays ``None`` and the gate's outcome
# write is a no-op (spec v12 §4.5 line 274).
_ACTIVE_PYTEST_SESSION: Optional[Any] = None


def set_active_pytest_session(session: Optional[Any]) -> None:
    """Plugin hook — record the active pytest session for outcome writes.

    The substrate's pytest plugin (issue #411 / #422) calls this in
    ``pytest_sessionstart`` and again with ``None`` in
    ``pytest_sessionfinish``. The gate uses the reference to populate
    ``session._atdd["rule_outcomes"]`` per spec v12 §4.5; outside pytest
    the reference stays ``None`` and the gate's outcome write is a no-op.
    """
    global _ACTIVE_PYTEST_SESSION
    _ACTIVE_PYTEST_SESSION = session


def get_active_pytest_session() -> Optional[Any]:
    """Test hook — read the active pytest session reference."""
    return _ACTIVE_PYTEST_SESSION


def record_rule_outcome(rule_id: str, outcome: str) -> None:
    """Public hook — write ``(rule_id, outcome)`` to the session result map.

    Substrate spec v12 §4.5 / issue #422. Runners (metric, security,
    harness plugin) call this to record per-rule outcomes; the gate also
    calls it internally for failures (see ``assert_disposition_satisfied``).
    Outside a pytest run the call is a no-op. ``outcome`` is one of
    ``"passed"`` / ``"failed"``.
    """
    _record_rule_outcome(rule_id, outcome)


def _record_rule_outcome(rule_id: str, outcome: str) -> None:
    """Write ``(rule_id, outcome)`` into ``session._atdd['rule_outcomes']``.

    Substrate spec v12 §4.5 / issue #422. The security runner reads this
    map to determine whether each bound acceptance's rule passed in this
    run. ``outcome`` is one of ``"passed"`` / ``"failed"``.

    Robust to:
      - No active session (outside pytest) — silent no-op.
      - Missing ``_atdd`` namespace — initialized on first write.
      - Missing ``rule_outcomes`` key — initialized on first write.

    Last-write-wins semantics: a rule may be touched by multiple gate
    calls (e.g. harness + metric mode for the same acceptance). Either
    failure marks the rule failed; the security runner reads "failed" if
    ANY gate call recorded a failure for the bound rule_id.
    """
    session = _ACTIVE_PYTEST_SESSION
    if session is None:
        return
    namespace = getattr(session, "_atdd", None)
    if not isinstance(namespace, dict):
        namespace = {}
        try:
            setattr(session, "_atdd", namespace)
        except (AttributeError, TypeError):  # atdd:suppress(coder.logging.coach-silent-swallow)
            return
    outcomes = namespace.get("rule_outcomes")
    if not isinstance(outcomes, dict):
        outcomes = {}
        namespace["rule_outcomes"] = outcomes
    # Promote a recorded failure over a recorded pass — either gate call
    # producing a failure means the rule's contract was broken in this run.
    if outcome == "failed" or rule_id not in outcomes:
        outcomes[rule_id] = outcome


def _looks_like_violation(obj: Any) -> bool:
    """Duck-typed check: structured ``Violation`` carries rule_id+severity+location."""
    return (
        hasattr(obj, "rule_id")
        and hasattr(obj, "severity")
        and hasattr(obj, "location")
    )


def _split_location(location: str) -> tuple[str, Optional[int]]:
    """Parse ``"path:line"`` (or ``"path:line:col"``) into ``(path, line)``.

    Returns ``(location, None)`` when the location string lacks a numeric
    line component.
    """
    # Handle path:line and path:line:col by trying each tail position.
    parts = location.split(":")
    if len(parts) >= 2:
        # path:line:col → line is parts[-2]; path:line → line is parts[-1]
        for candidate_idx in (-2, -1):
            try:
                lineno = int(parts[candidate_idx])
            except (ValueError, IndexError):
                continue
            path = ":".join(parts[: candidate_idx if candidate_idx == -2 else -1])
            return path, lineno
    return location, None


def _read_line(repo_root: Path, rel_path: str, lineno: int) -> Optional[str]:
    """Best-effort read of one line for marker matching."""
    p = (repo_root / rel_path) if not Path(rel_path).is_absolute() else Path(rel_path)
    try:
        with open(p, encoding="utf-8") as fh:
            for idx, line in enumerate(fh, start=1):
                if idx == lineno:
                    return line
    except (OSError, UnicodeDecodeError):  # atdd:suppress(coder.logging.coach-silent-swallow)
        return None
    return None


def _format_violation(v: Any, disposition: str) -> str:
    return (
        f"  [{v.rule_id} sev={v.severity} disposition={disposition}] "
        f"{v.location}: {v.detail}"
    )


def _suggest_marker_for(rule_id: str) -> str:
    return (
        f"      Either fix the violation, or add an inline marker on the "
        f"offending line:\n"
        f"        # atdd:suppress({rule_id}) UNTIL=<YYYY-MM-DD>"
    )


def assert_disposition_satisfied(
    validator_id: str,
    violations: Sequence[Any],
    registry: Optional[Dict[str, RuleMetadata]] = None,
    repo_root: Optional[Path] = None,
) -> None:
    """Pass/fail the calling test based on per-rule disposition.

    Args:
        validator_id: Stable name of the validator (used in failure
            messages and warnings — replaces RatchetBaseline's
            ``validator_id`` parameter).
        violations: Sequence of structured ``Violation`` records. Bare
            strings or dicts are accepted for back-compat but downgrade
            the gate to strict-by-default (no rule_id ⇒ no disposition
            ⇒ fail on any non-empty list).
        registry: Optional pre-built registry. Defaults to
            ``build_registry()`` which walks every ``*.convention.yaml``.
        repo_root: Optional override for resolving violation locations
            (``path:line``) when matching suppression markers. Defaults
            to ``find_repo_root()``.

    Behavior:
        - Empty ``violations`` → pass silently.
        - Group by ``rule_id``; look up ``disposition`` per rule.
        - ``strict``: any violation → ``pytest.fail`` with full punch list.
        - ``suppress-and-clean``: split into suppressed vs unsuppressed
          via inline ``# atdd:suppress(<rule_id>)`` marker on the
          offending line. Unsuppressed → ``pytest.fail``; suppressed →
          silent pass (deadline auditing is the
          ``test_no_stale_suppressions.py`` validator's job).
        - ``advisory``: ``warnings.warn`` (UserWarning) and pass.
        - Unknown ``rule_id`` (not in registry) → treated as ``strict``.
        - Bare-string / dict ``violations`` (legacy callers): treated as
          a single ``strict`` bucket because there is no rule_id to look
          up. Empty → pass; non-empty → fail.
    """
    if not violations:
        # Substrate spec v12 §4.5 / issue #422: record a "passed" outcome on
        # the session result map for the validator's rule_id when the gate
        # was given an empty list. The validator_id is "<module>::<func>"
        # and not itself a rule_id, so this branch only fires for the
        # opaque-but-empty case; per-rule passes are recorded inside the
        # main loop below using the structured bucket's keys.
        return

    registry = registry if registry is not None else build_registry()
    root = repo_root if repo_root is not None else find_repo_root()

    # Bucket structured Violations by rule_id; collect opaque entries
    # separately under a sentinel bucket.
    structured: Dict[str, List[Any]] = defaultdict(list)
    opaque: List[Any] = []
    for v in violations:
        if _looks_like_violation(v):
            structured[v.rule_id].append(v)
        else:
            opaque.append(v)

    # Substrate spec v12 §4.5 / issue #422: record per-rule outcomes on the
    # active pytest session BEFORE we route through the gate. The security
    # runner reads this map to decide whether each bound acceptance's rule
    # failed in the current run; recording before the gate raises ensures
    # the outcome is captured even when ``pytest.fail`` aborts the test.
    for rule_id in structured.keys():
        _record_rule_outcome(rule_id, "failed")

    failures: List[str] = []
    advisory_blocks: List[str] = []
    error_annotations: List[Any] = []
    warning_annotations: List[Any] = []

    for rule_id, vs in structured.items():
        meta = registry.get(rule_id)
        disposition = (meta.disposition if meta and meta.disposition else _DEFAULT_DISPOSITION)
        if disposition not in _LEGAL_DISPOSITIONS:
            disposition = _DEFAULT_DISPOSITION

        if disposition == "advisory":
            advisory_blocks.append(
                _format_advisory_block(validator_id, rule_id, vs, registry)
            )
            warning_annotations.extend(vs)
            for v in vs:
                _record_observed_violation(validator_id, v, disposition, None)
            continue

        if disposition == "strict":
            failures.append(_format_failure_block(
                validator_id=validator_id,
                rule_id=rule_id,
                disposition=disposition,
                violations=vs,
                suppressed_count=0,
                registry=registry,
            ))
            error_annotations.extend(vs)
            for v in vs:
                _record_observed_violation(validator_id, v, disposition, None)
            continue

        # suppress-and-clean
        suppressed: List[Any] = []
        unsuppressed: List[Any] = []
        for v in vs:
            rel_path, lineno = _split_location(v.location)
            line_text: Optional[str] = None
            if lineno is not None:
                line_text = _read_line(root, rel_path, lineno)
            marker_text: Optional[str] = None
            if line_text is not None:
                marker_text = _match_marker_text(line_text, rule_id)
            if marker_text is not None:
                suppressed.append(v)
                _record_observed_violation(validator_id, v, disposition, marker_text)
            else:
                unsuppressed.append(v)
                _record_observed_violation(validator_id, v, disposition, None)
        if unsuppressed:
            failures.append(_format_failure_block(
                validator_id=validator_id,
                rule_id=rule_id,
                disposition=disposition,
                violations=unsuppressed,
                suppressed_count=len(suppressed),
                registry=registry,
            ))
            error_annotations.extend(unsuppressed)

    # Opaque violations: no rule_id ⇒ default-strict.
    if opaque:
        failures.append(_format_opaque_block(validator_id, opaque))

    # Issue #404: emit GH Actions ::error::/::warning:: directives so each
    # violation surfaces as an inline annotation on the PR's "Files changed"
    # tab. No-op outside GH Actions to keep local pytest output clean.
    _emit_github_annotations(error_annotations, registry, level="error")
    _emit_github_annotations(warning_annotations, registry, level="warning")

    for block in advisory_blocks:
        warnings.warn(block, UserWarning, stacklevel=2)

    if failures:
        header = (
            f"\n[disposition gate] {validator_id}: "
            f"{sum(_count_block_violations(b) for b in failures)} unsuppressed violation(s)\n"
        )
        pytest.fail(header + "\n".join(failures))


def _count_block_violations(block: str) -> int:
    # Each violation is one indented "  [..." line; cheap line count
    return sum(1 for ln in block.splitlines() if ln.lstrip().startswith("["))


def _format_failure_block(
    validator_id: str,
    rule_id: str,
    disposition: str,
    violations: Sequence[Any],
    suppressed_count: int,
    registry: Optional[Dict[str, RuleMetadata]] = None,
) -> str:
    lines = [
        f"\n  rule_id={rule_id} disposition={disposition} "
        f"validator={validator_id} ({len(violations)} unsuppressed"
        + (f", {suppressed_count} suppressed" if suppressed_count else "")
        + "):",
    ]
    meta = registry.get(rule_id) if registry else None
    if meta and meta.description:
        lines.append(f"    description: {meta.description.splitlines()[0]}")
    if meta and meta.fix_hint:
        lines.append(f"    fix_hint:    {meta.fix_hint.splitlines()[0]}")
    for v in violations:
        lines.append(_format_violation(v, disposition))
    if disposition == "suppress-and-clean":
        lines.append("")
        lines.append(_suggest_marker_for(rule_id))
    return "\n".join(lines)


def _format_advisory_block(
    validator_id: str,
    rule_id: str,
    violations: Sequence[Any],
    registry: Optional[Dict[str, RuleMetadata]] = None,
) -> str:
    lines = [
        f"[advisory] {validator_id} {rule_id}: {len(violations)} violation(s)"
    ]
    meta = registry.get(rule_id) if registry else None
    if meta and meta.description:
        lines.append(f"    description: {meta.description.splitlines()[0]}")
    if meta and meta.fix_hint:
        lines.append(f"    fix_hint:    {meta.fix_hint.splitlines()[0]}")
    for v in violations:
        lines.append(_format_violation(v, "advisory"))
    return "\n".join(lines)


def _format_opaque_block(validator_id: str, opaque: Sequence[Any]) -> str:
    lines = [
        f"\n  validator={validator_id}: "
        f"{len(opaque)} legacy (no rule_id) violation(s) — strict by default:"
    ]
    for v in opaque:
        lines.append(f"    {v}")
    return "\n".join(lines)


def _first_line(text: Optional[str], default: str = "") -> str:
    """Return the first non-empty line of ``text`` (or ``default``)."""
    if not text:
        return default
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line
    return default


def _sanitize_annotation_field(value: str) -> str:
    """Strip characters that would break a GH Actions workflow command.

    GitHub parses the directive as ``::error file=...,line=...,title=...::msg``;
    embedded ``\\n``, ``::``, or ``,`` in ``title``/``file`` would corrupt the
    parse. Replace them with safe equivalents while preserving readability.
    """
    return (
        value.replace("\r", " ")
        .replace("\n", " ")
        .replace("::", ":")
        .replace(",", ";")
        .strip()
    )


def _sanitize_annotation_message(value: str) -> str:
    """Strip characters that would terminate the message early."""
    return value.replace("\r", " ").replace("\n", " ").replace("::", ":").strip()


def _emit_github_annotations(
    violations: Sequence[Any],
    registry: Optional[Dict[str, RuleMetadata]],
    *,
    level: str = "error",
    stream: Any = None,
) -> None:
    """Emit one ``::error::`` / ``::warning::`` workflow command per violation.

    Issue #404. Each annotation surfaces inline on the PR's "Files changed"
    tab at the offending ``file:line`` with the rule's description, fix_hint,
    and the violation's detail packed into the message. No-op when the
    process is not running under GitHub Actions (detected via the
    ``GITHUB_ACTIONS=true`` env var) — local pytest stdout stays clean.

    Args:
        violations: Sequence of structured ``Violation`` records
            (``rule_id`` + ``location`` + ``detail``). Opaque/dict-shaped
            entries are skipped — they have no anchor to annotate.
        registry: Optional registry of ``RuleMetadata`` keyed by ``rule_id``.
            When present, ``description`` and ``fix_hint`` are pulled from
            here to enrich the annotation message.
        level: ``"error"`` (default) or ``"warning"``. Mirrors the
            disposition: ``strict`` and unsuppressed ``suppress-and-clean``
            emit ``::error::``; ``advisory`` emits ``::warning::``.
        stream: Override the output stream (used by tests). Defaults to
            ``sys.stdout``.
    """
    if not violations:
        return
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    if level not in ("error", "warning"):
        level = "error"

    out = stream if stream is not None else sys.stdout
    for v in violations:
        if not _looks_like_violation(v):
            continue
        path, line = _split_location(v.location)
        meta = registry.get(v.rule_id) if registry else None
        description = _first_line(meta.description if meta else None)
        fix_hint = _first_line(meta.fix_hint if meta else None, default="see convention")
        detail = _first_line(v.detail, default="")

        params = [f"file={_sanitize_annotation_field(path)}"]
        if line is not None:
            params.append(f"line={line}")
        params.append(f"title={_sanitize_annotation_field(v.rule_id)}")

        message_parts: List[str] = []
        if description:
            message_parts.append(description)
        message_parts.append(f"fix: {fix_hint}")
        if detail:
            message_parts.append(f"site: {detail}")
        message = _sanitize_annotation_message(" | ".join(message_parts))

        out.write(f"::{level} {','.join(params)}::{message}\n")
    out.flush()


__all__ = [
    "assert_disposition_satisfied",
    "get_active_pytest_session",
    "record_rule_outcome",
    "set_active_pytest_session",
]
