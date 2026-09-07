# URN: test:self-compliance:pr-scope-routing:PRSCOPE-UNIT-001-pr-scanning-gates-route-through-pr-scope
# Phase: RED
# Layer: unit
# Assertion: structural
# Runtime: python
"""PRSCOPE-UNIT-001 — a gate that scans every open PR must scope its verdict.

    Any validator that enumerates open pull requests AND fails on `PR#<n>`
    locations must route those violations through `_pr_scope`.

`_pr_scope` exists because an unscoped PR-scanning gate "fails a branch for a
state it neither created nor can fix" (#1478/E070). It fixed two gates; #1791
fixed a third when `coach.pr.early-phase-ships-code` re-opened the hole; and
`coach.pr.base-must-be-default-branch` reded every branch in the repo until
#1802 narrowed the rule. Routing is a convention nobody enforces, so each new
gate re-opens it, and the person who sees the red is never the person who
caused it.

WHY THE DISCRIMINATOR IS ENUMERATION, NOT THE LOCATION SHAPE. Emitting a
`PR#<n>` location is not the signal: `test_e009_runtime_artifacts_blocked`
emits one while scanning only the CURRENT branch's own `git diff`, so scoping it
would be wrong and, when no PR resolves, would silently stop it blocking. The
signal is asking GitHub for *other people's* pull requests.

This validator reads source text. It does not import the modules it inspects:
importing a validator module executes its module-scope `bind_rule` and, for the
live gates, can reach the network.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import List

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.config import resolve_code_root
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

_RULE = bind_rule("coach.pr.scanning-gate-must-scope-to-current-pr")

#: This validator reads the toolkit's OWN source, so it is a platform self-test
#: and resolves the toolkit root through the declared seam rather than hardcoding
#: `src/atdd` (`resolve_code_root` is "the single seam validators use instead of
#: hardcoding"). A consumer repo declares no `code.toolkit`, so the scan is empty
#: there and the gate is correctly a no-op.
pytestmark = pytest.mark.platform

REPO_ROOT = find_repo_root()
_TOOLKIT_ROOT = resolve_code_root("toolkit", REPO_ROOT)
_VALIDATOR_DIR = (
    (_TOOLKIT_ROOT / "coach" / "validators") if _TOOLKIT_ROOT else None
)

#: Asking GitHub for pull requests other than this branch's own.
_ENUMERATES = re.compile(
    r"""fetch_open_prs|list_open_prs|_fetch_open_pr_numbers"""
    r"""|["']pr["']\s*,\s*["']list["']""",
)

#: Failing on a location that names a specific PR.
_PR_LOCATION = re.compile(r"""location\s*=\s*f?["']PR#\{""")

#: Routing that narrowing through the shared selector.
_ROUTES = re.compile(r"select_for_current_pr|select_blocking_violations")

#: `_pr_scope` itself, and the tests that exercise it with synthetic data.
_EXEMPT = {"_pr_scope.py"}


def _rel(path: Path) -> str:
    """Repo-relative when possible; the synthetic-fixture tests pass a tmp dir."""
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return path.name


def scan_unscoped_pr_gates(validator_dir: Path) -> List[Violation]:
    """One Violation per validator that enumerates open PRs without scoping."""
    violations: List[Violation] = []
    for path in sorted(validator_dir.glob("*.py")):
        if path.name in _EXEMPT:
            continue
        try:
            src = path.read_text(encoding="utf-8")
        except OSError:
            continue
        if not (_ENUMERATES.search(src) and _PR_LOCATION.search(src)):
            continue
        if _ROUTES.search(src):
            continue
        violations.append(Violation(
            rule_id=_RULE.rule_id,
            severity=_RULE.severity,
            location=f"{_rel(path)}:1",
            detail=(
                f"{path.name} enumerates open pull requests and fails on PR#<n> "
                "locations, but never routes through atdd.coach.validators._pr_scope. "
                "Without it, one offending PR fails every other contributor's CI — "
                "cross-PR coupling rather than enforcement (#1478/E070). Wrap the "
                "scan result in select_for_current_pr(violations, current_pr) before "
                "handing it to assert_disposition_satisfied."
            ),
            fix_hint_ref=_RULE.fix_hint_ref,
        ))
    return violations


def test_every_pr_scanning_gate_routes_through_pr_scope() -> None:
    """SPEC: coach.pr.scanning-gate-must-scope-to-current-pr."""
    if _VALIDATOR_DIR is None or not _VALIDATOR_DIR.is_dir():
        pytest.skip("no code.toolkit declared — not the toolkit's own checkout")
    assert_disposition_satisfied(
        validator_id="pr_scope_routing",
        violations=scan_unscoped_pr_gates(_VALIDATOR_DIR),
    )


def test_detector_flags_a_synthetic_unscoped_gate(tmp_path: Path) -> None:
    """The detector must actually fire — a scan that never reports is a no-op."""
    bad = tmp_path / "test_bad_gate.py"
    bad.write_text(
        'prs = mgr.fetch_open_prs()\n'
        'v = Violation(location=f"PR#{n}:0")\n'
    )
    assert len(scan_unscoped_pr_gates(tmp_path)) == 1


def test_detector_ignores_a_scoped_gate(tmp_path: Path) -> None:
    good = tmp_path / "test_good_gate.py"
    good.write_text(
        'prs = mgr.fetch_open_prs()\n'
        'v = Violation(location=f"PR#{n}:0")\n'
        'blocking = select_for_current_pr(v, current_pr)\n'
    )
    assert scan_unscoped_pr_gates(tmp_path) == []


def test_detector_ignores_a_gate_that_scans_only_its_own_branch(tmp_path: Path) -> None:
    """`e009` emits PR#<n> locations from its own `git diff` — not a PR scan."""
    own = tmp_path / "test_own_branch.py"
    own.write_text(
        'changed = _fetch_diff_files_via_git(root, default_branch)\n'
        'v = Violation(location=f"PR#{pr_number}:{path}")\n'
    )
    assert scan_unscoped_pr_gates(tmp_path) == []


# --------------------------------------------------------------------------- #
# Scoping narrows WHO fails, never WHETHER something is a violation. Proven on
# synthetic violations because #1802's stacked-PR allowance means the live scan
# currently reports none — a scoping change that quietly stopped blocking would
# look identical to a clean repo, which is the failure mode worth guarding.
# --------------------------------------------------------------------------- #


_BASE_RULE = bind_rule("coach.pr.base-must-be-default-branch")


def _base_violation(pr_number: int) -> Violation:
    return Violation(
        rule_id=_BASE_RULE.rule_id,
        severity=_BASE_RULE.severity,
        location=f"PR#{pr_number}:0",
        detail=f"PR #{pr_number} targets a non-default base",
    )


def test_scoping_still_blocks_the_offender_on_its_own_run() -> None:
    from atdd.coach.validators._pr_scope import select_for_current_pr

    offenders = [_base_violation(1799), _base_violation(1806)]
    blocking = select_for_current_pr(offenders, current_pr=1799)
    assert [v.location for v in blocking] == ["PR#1799:0"], (
        "an offending PR must still fail its own run; scoping narrows who fails, "
        "never whether the violation stands"
    )


def test_scoping_spares_an_innocent_pr() -> None:
    from atdd.coach.validators._pr_scope import select_for_current_pr

    offenders = [_base_violation(1799), _base_violation(1806)]
    assert select_for_current_pr(offenders, current_pr=1804) == []


def test_base_branch_locations_carry_the_prefix_the_selector_matches() -> None:
    """The gate emitted bare `PR#<n>` before #1805.

    `_pr_scope.pr_location_prefix` matches `PR#<n>:`, so routing alone would have
    left the gate unscoped in practice — every violation would have failed the
    prefix test and been dropped for every PR, including the offender's own run.
    """
    from atdd.coach.validators._pr_scope import pr_location_prefix

    assert _base_violation(1799).location.startswith(pr_location_prefix(1799))
