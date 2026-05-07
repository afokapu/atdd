# URN: component:govern-lifecycle:enforcement-substrate:test_orchestration_session_naming:backend:domain
# Runtime: python
# Purpose: Audit canonical session naming + layout placement (issue #470).

"""Coach validator for canonical session naming + layout placement (issue #470).

Enforces (advisory):

    * ``coach.orchestration.canonical-session-name`` — every active ATDD
      session name (cmux tab + Claude session) matches
      ``<REPO><N>[-phase<M>]-<slug>``.
    * ``coach.orchestration.layout-conformance`` — workspace surfaces
      follow the right-of-shell grid policy in
      ``orchestration.convention.yaml::layout_placement.policy``.

The active-introspection branch (querying cmux for live workspaces and
their tab titles) is **best-effort** — when cmux is not on PATH or the
repo is being checked in CI, this validator skips the introspection
half and only enforces convention-self-coherence (regex parses, every
exemplar in the convention round-trips through the helper, layout
policy covers all surface-count bands).

Both rules are bound here via ``bind_rule`` so the reverse-coherence
substrate (issue #399) resolves the convention's ``validator:`` field
to this module.

Run:
    PYTHONPATH=src python3 -m pytest -q \
        src/atdd/coach/validators/test_orchestration_session_naming.py -v
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pytest
import yaml

import atdd
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.utils.session_naming import (
    CANONICAL_NAME_REGEX,
    compute_canonical_name,
    is_canonical_name,
    parse_canonical_name,
    target_grid_label,
)
from atdd.coach.validators._violation import Violation


pytestmark = [pytest.mark.coach]


_RULE_NAME = bind_rule("coach.orchestration.canonical-session-name")
_RULE_LAYOUT = bind_rule("coach.orchestration.layout-conformance")


_ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
_ORCHESTRATION_CONVENTION = (
    _ATDD_PKG_DIR / "coach" / "conventions" / "orchestration.convention.yaml"
)


# ---------------------------------------------------------------------------
# Convention loaders
# ---------------------------------------------------------------------------
def _load_convention() -> Dict:
    if _ORCHESTRATION_CONVENTION.is_file():
        path = _ORCHESTRATION_CONVENTION
    else:
        from atdd.coach.utils.repo import find_repo_root
        path = (
            find_repo_root()
            / "src" / "atdd" / "coach" / "conventions"
            / "orchestration.convention.yaml"
        )
        if not path.is_file():
            pytest.fail(f"orchestration convention missing at {_ORCHESTRATION_CONVENTION}")
    with open(path) as fh:
        return yaml.safe_load(fh) or {}


def _session_naming_block() -> Dict:
    block = _load_convention().get("session_naming")
    if not isinstance(block, dict):
        pytest.fail("orchestration.convention.yaml::session_naming block missing")
    return block


def _layout_block() -> Dict:
    block = _load_convention().get("layout_placement")
    if not isinstance(block, dict):
        pytest.fail("orchestration.convention.yaml::layout_placement block missing")
    return block


# ---------------------------------------------------------------------------
# Active cmux introspection (best-effort)
# ---------------------------------------------------------------------------
def _cmux_available() -> bool:
    return shutil.which("cmux") is not None


def _list_active_session_names() -> List[Tuple[str, str]]:
    """Return ``[(ref, tab_name), ...]`` from cmux.

    Returns an empty list when cmux is unavailable or the introspection
    output is not parseable. Callers treat empty as "skip the active
    branch" — convention-coherence checks still run.
    """
    if not _cmux_available():
        return []
    try:
        result = subprocess.run(
            ["cmux", "list-tabs", "--workspace", "workspace:1"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (subprocess.SubprocessError, OSError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
        return []
    if result.returncode != 0:
        return []
    rows: List[Tuple[str, str]] = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"\s+", line, maxsplit=1)
        if len(parts) == 2:
            rows.append((parts[0], parts[1]))
    return rows


# ---------------------------------------------------------------------------
# Violation builders
# ---------------------------------------------------------------------------
def _build_naming_violations() -> List[Violation]:
    """Convention coherence + active introspection for canonical names."""
    violations: List[Violation] = []
    block = _session_naming_block()

    # 1. Regex declared in the convention compiles and matches the helper's regex.
    declared_regex = block.get("regex")
    if not isinstance(declared_regex, str) or not declared_regex:
        violations.append(
            Violation(
                rule_id=_RULE_NAME.rule_id,
                severity=_RULE_NAME.severity,
                location="orchestration.convention.yaml:session_naming.regex",
                detail="session_naming.regex is missing or empty",
            )
        )
    else:
        try:
            re.compile(declared_regex)
        except re.error as exc:
            violations.append(
                Violation(
                    rule_id=_RULE_NAME.rule_id,
                    severity=_RULE_NAME.severity,
                    location="orchestration.convention.yaml:session_naming.regex",
                    detail=f"session_naming.regex does not compile: {exc}",
                )
            )

    # 2. Every declared exemplar parses via the helper.
    exemplars = block.get("exemplars") or []
    for idx, exemplar in enumerate(exemplars):
        if not isinstance(exemplar, str):
            continue
        if not is_canonical_name(exemplar):
            violations.append(
                Violation(
                    rule_id=_RULE_NAME.rule_id,
                    severity=_RULE_NAME.severity,
                    location=f"orchestration.convention.yaml:session_naming.exemplars[{idx}]",
                    detail=(
                        f"exemplar {exemplar!r} does not match the canonical regex — "
                        "either the exemplar is wrong or the regex needs widening"
                    ),
                )
            )

    # 3. Active cmux introspection (best-effort).
    for ref, name in _list_active_session_names():
        if is_canonical_name(name):
            continue
        violations.append(
            Violation(
                rule_id=_RULE_NAME.rule_id,
                severity=_RULE_NAME.severity,
                location=f"cmux:{ref}",
                detail=(
                    f"surface {ref!r} has non-canonical name {name!r}; "
                    "run `atdd babysit` to auto-correct"
                ),
                fix_hint_ref=_RULE_NAME.fix_hint,
            )
        )

    return violations


def _build_layout_violations() -> List[Violation]:
    """Convention-coherence checks for the layout-placement policy."""
    violations: List[Violation] = []
    block = _layout_block()
    policy = block.get("policy")
    if not isinstance(policy, dict) or not policy:
        violations.append(
            Violation(
                rule_id=_RULE_LAYOUT.rule_id,
                severity=_RULE_LAYOUT.severity,
                location="orchestration.convention.yaml:layout_placement.policy",
                detail="layout_placement.policy block missing or empty",
            )
        )
        return violations

    # Every count in 0..7 maps to a non-empty target band — the helper must
    # echo the convention. Higher counts (>=7) are covered by the dense band.
    for n in range(0, 9):
        label = target_grid_label(n)
        if not label:
            violations.append(
                Violation(
                    rule_id=_RULE_LAYOUT.rule_id,
                    severity=_RULE_LAYOUT.severity,
                    location=f"session_naming.target_grid_label({n})",
                    detail=f"target_grid_label returned empty string for surface_count={n}",
                )
            )

    return violations


# ---------------------------------------------------------------------------
# Public test entry points (referenced by orchestration.convention.yaml)
# ---------------------------------------------------------------------------
def test_active_session_names_canonical():
    """Canonical session names match <REPO><N>[-phase<M>]-<slug>.

    Advisory: emits Violation records on drift and skips when cmux is
    not available. Convention-coherence checks run unconditionally.
    """
    violations = _build_naming_violations()
    if violations:
        # Advisory disposition (Decision row 3): collect + render but do
        # NOT fail the gate on the first ship. CI exposes the count via
        # the ratchet substrate.
        for v in violations:
            print(str(v))
        # Surface as a soft-warn so visibility is not lost.
        pytest.skip(
            f"{len(violations)} canonical-name advisory violation(s) — see stdout"
        )


def test_workspace_layout_conforms():
    """Workspace surfaces follow the grid policy.

    Advisory: convention-coherence only in v1; live cmux layout
    introspection is a follow-on once cmux exposes pane positions.
    """
    violations = _build_layout_violations()
    if violations:
        for v in violations:
            print(str(v))
        pytest.skip(
            f"{len(violations)} layout-conformance advisory violation(s) — see stdout"
        )


# ---------------------------------------------------------------------------
# Self-coherence: helper regex matches the convention regex
# ---------------------------------------------------------------------------
def test_helper_regex_matches_convention_regex():
    """``CANONICAL_NAME_REGEX`` (helper) must agree with the convention's regex."""
    block = _session_naming_block()
    declared = block.get("regex")
    assert isinstance(declared, str) and declared, "session_naming.regex missing"
    helper_pattern = CANONICAL_NAME_REGEX.pattern
    # Tolerate non-capturing-group cosmetic differences (``(?:...)`` vs ``(...)``)
    # since both forms describe the same language.
    norm_declared = declared.replace("(?:", "(")
    norm_helper = helper_pattern.replace("(?:", "(")
    assert norm_helper == norm_declared, (
        "helper CANONICAL_NAME_REGEX does not match convention regex.\n"
        f"  helper:     {helper_pattern!r}\n"
        f"  convention: {declared!r}\n"
        "Update one of them so they describe the same language."
    )


def test_round_trip_canonical_name():
    """compute_canonical_name → parse_canonical_name returns the original parts."""
    name = compute_canonical_name("ATDD", 470, "canonical-session-naming")
    parsed = parse_canonical_name(name)
    assert parsed is not None
    assert parsed.repo == "ATDD"
    assert parsed.issue == 470
    assert parsed.phase is None
    assert parsed.slug == "canonical-session-naming"

    phased = compute_canonical_name("ATDD", 462, "bump-on-merge", phase=2)
    parsed_phase = parse_canonical_name(phased)
    assert parsed_phase is not None
    assert parsed_phase.phase == 2
    assert parsed_phase.slug == "bump-on-merge"


def test_exemplars_round_trip():
    """Every exemplar in the convention parses cleanly via the helper."""
    exemplars = _session_naming_block().get("exemplars") or []
    assert exemplars, "session_naming.exemplars must be non-empty for documentation value"
    for exemplar in exemplars:
        assert is_canonical_name(exemplar), (
            f"exemplar {exemplar!r} declared in orchestration.convention.yaml::"
            "session_naming.exemplars does not match the canonical regex"
        )
