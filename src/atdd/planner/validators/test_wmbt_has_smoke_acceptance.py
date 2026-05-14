"""
planner.wmbt.must-have-smoke-acceptance validator (issue #681).

Mirrors the tester-side TESTER-SMOKE-PRES-001 pattern. Walks every WMBT
YAML under ``plan/<wagon>/*.yaml`` and emits one structured Violation per
WMBT whose acceptance URN list contains zero entries with a SMOKE harness
token (``-SMOKE-NNN[-slug]``).

Disposition is ``suppress-and-clean``: docs-only WMBTs that have no real
infrastructure to verify can opt out by adding
``# atdd:suppress(planner.wmbt.must-have-smoke-acceptance) UNTIL=YYYY-MM-DD``
on the WMBT YAML's ``urn:`` line. The disposition gate reads that marker.

Convention: ``src/atdd/planner/conventions/wmbt.convention.yaml``
            (rule ``planner.wmbt.must-have-smoke-acceptance``).

Run: ``atdd validate planner``
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import pytest
import yaml

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.planner]


_RULE = bind_rule("planner.wmbt.must-have-smoke-acceptance")
_VALIDATOR_ID = "wmbt_has_smoke_acceptance"

REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"

# WMBT filename grammar — same as shared_fixtures.wmbt_files
_WMBT_FILENAME_RE = re.compile(r"^[DLPCEMYRK]\d{3}\.yaml$")

# A SMOKE acceptance URN ends with the literal harness token "-SMOKE-NNN"
# (optionally followed by a kebab slug). See
# src/atdd/planner/conventions/acceptance.convention.yaml::urn for the
# canonical pattern; SMOKE is not currently in the schema enum but is
# in active use across plan/ (e.g. plan/integration_hardening/E001.yaml).
_SMOKE_URN_RE = re.compile(
    r"^acc:[a-z][a-z0-9-]*:[DLPCEMYRK]\d{3}-SMOKE-\d{3}(?:-[a-z0-9-]+)?$"
)


def iter_wmbt_files(plan_dir: Path) -> List[Tuple[Path, Dict[str, Any]]]:
    """Walk ``plan_dir/<wagon>/*.yaml`` for WMBT files. Pure I/O — no fixture."""
    if not plan_dir.exists():
        return []
    out: List[Tuple[Path, Dict[str, Any]]] = []
    for wagon_dir in sorted(plan_dir.iterdir()):
        if not wagon_dir.is_dir() or wagon_dir.name.startswith("_"):
            continue
        for yaml_file in sorted(wagon_dir.glob("*.yaml")):
            if not _WMBT_FILENAME_RE.match(yaml_file.name):
                continue
            try:
                with open(yaml_file) as fh:
                    data = yaml.safe_load(fh) or {}
            except (OSError, yaml.YAMLError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
                continue
            if isinstance(data, dict):
                out.append((yaml_file, data))
    return out


def extract_acceptance_urns(wmbt_data: Dict[str, Any]) -> List[str]:
    """Return the list of acceptance URN strings declared on this WMBT."""
    urns: List[str] = []
    for acc in wmbt_data.get("acceptances", []) or []:
        if isinstance(acc, dict):
            identity = acc.get("identity") or {}
            urn = identity.get("urn")
            if isinstance(urn, str) and urn:
                urns.append(urn)
        elif isinstance(acc, str) and acc:
            urns.append(acc)
    return urns


def has_smoke_urn(urns: Iterable[str]) -> bool:
    """True if any URN in *urns* matches the SMOKE harness token grammar."""
    return any(_SMOKE_URN_RE.match(u) for u in urns)


def _find_urn_lineno(yaml_path: Path) -> int:
    """Return the 1-based line number of the WMBT's ``urn:`` declaration.

    Falls back to line 1 when the file can't be read or the line isn't
    found (defensive — the validator must always emit a usable location
    so suppression-marker scanning has something to anchor on).
    """
    try:
        with open(yaml_path) as fh:
            for idx, line in enumerate(fh, start=1):
                stripped = line.lstrip()
                if stripped.startswith("urn:"):
                    return idx
    except OSError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        pass
    return 1


def evaluate_wmbt_smoke_coverage(
    wmbt_files: Sequence[Tuple[Path, Dict[str, Any]]],
    repo_root: Path,
) -> List[Violation]:
    """Pure evaluator: emit one Violation per WMBT with zero SMOKE URNs.

    Pure function — no I/O against repo state other than the WMBT files
    already loaded by the caller — so the helper-tests file can drive it
    from synthetic ``(path, dict)`` fixtures without writing to disk.
    """
    violations: List[Violation] = []
    for path, data in wmbt_files:
        urns = extract_acceptance_urns(data)
        if has_smoke_urn(urns):
            continue
        wmbt_urn = data.get("urn") or ""
        try:
            rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = path.as_posix()
        lineno = _find_urn_lineno(path)
        detail = (
            f"WMBT {wmbt_urn or path.stem} declares "
            f"{len(urns)} acceptance URN(s) but none use the SMOKE harness "
            f"token ('-SMOKE-NNN'). Add an acceptance whose urn matches "
            f"'acc:<wagon>:<wmbt_id>-SMOKE-NNN[-<slug>]' with phase: SMOKE, "
            f"or suppress on this line if the WMBT is docs-only "
            f"(see fix_hint for the inline marker)."
        )
        violations.append(
            Violation(
                rule_id=_RULE.rule_id,
                severity=_RULE.severity,
                location=f"{rel}:{lineno}",
                detail=detail,
                fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
            )
        )
    return violations


def scan_plan_for_smoke_coverage(
    plan_dir: Optional[Path] = None,
    repo_root: Optional[Path] = None,
) -> List[Violation]:
    """End-to-end scanner: load every WMBT yaml, emit Violations."""
    root = repo_root or REPO_ROOT
    pdir = plan_dir or (root / "plan")
    return evaluate_wmbt_smoke_coverage(iter_wmbt_files(pdir), root)


# ---------------------------------------------------------------------------
# Test
# ---------------------------------------------------------------------------


def test_every_wmbt_has_smoke_acceptance():
    """
    SPEC: ``wmbt.convention.yaml::rules[planner.wmbt.must-have-smoke-acceptance]``.

    Given: Every WMBT YAML under ``plan/<wagon>/``.
    When:  Inspecting the WMBT's acceptance URN list.
    Then:  At least one URN uses the SMOKE harness token. WMBTs with zero
           SMOKE URNs surface as structured Violations the disposition
           gate fails on (unless inline-suppressed on the urn: line).
    """
    violations = scan_plan_for_smoke_coverage()
    assert_disposition_satisfied(
        validator_id=_VALIDATOR_ID,
        violations=violations,
    )
