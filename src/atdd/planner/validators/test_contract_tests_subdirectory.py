# Phase: RED
# Layer: backend.integration
"""planner.interface.tests-subdirectory validator (#1639).

Every schema-bearing leaf directory under ``contracts/`` or ``telemetry/`` must
carry a ``tests/`` subdirectory. A contract that ships a schema with no tests
beside it is a shape nobody checks.

Disposition is ``advisory``: the rule was declared by #1111 and enforced by
nothing, so all 6 schema-bearing directories in the live corpus are missing
``tests/``. Blocking on that would gate every contract edit behind a backfill
this issue is not scoped to do.

Chosen over ``planner.interface.orphan-detection``, which #1639 measured as
unbindable in either reading: its literal subject (the ``urn:`` field on
produce/consume entries) has **0** instances in the corpus, so it would be green
only because it is empty; and read against the ``contract:`` field instead it
restates ``planner.contract.registry-coherence``, which already reports that
class advisory. See the #1639 audit §3.

Convention: src/atdd/planner/conventions/nodes/planner.interface.tests-subdirectory.convention.yaml
Rule:       planner.interface.tests-subdirectory
Run:        atdd validate planner
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable, List

import pytest

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

_log = logging.getLogger(__name__)

pytestmark = [pytest.mark.planner]

_RULE = bind_rule("planner.interface.tests-subdirectory")
_VALIDATOR_ID = "contract_tests_subdirectory"

REPO_ROOT = find_repo_root()
_ROOTS = ("contracts", "telemetry")


def schema_bearing_dirs(root: Path) -> List[Path]:
    """Directories under *root* that directly hold at least one ``.json`` file.

    ``tests/`` directories are themselves excluded — a fixture folder is not a
    contract directory needing its own tests folder.
    """
    if not root.is_dir():
        return []
    out: List[Path] = []
    for d in sorted(root.rglob("*")):
        if not d.is_dir() or d.name == "tests":
            continue
        try:
            if any(p.suffix == ".json" for p in d.iterdir() if p.is_file()):
                out.append(d)
        except OSError as exc:
            _log.info(
                "tests-subdirectory scan skipped an unreadable directory",
                extra={"path": str(d), "error": str(exc).splitlines()[0][:160]},
            )
            continue
    return out


def _missing_tests_violation(d: Path, *, root: Path) -> Violation:
    try:
        loc = str(d.relative_to(root))
    except ValueError:
        loc = str(d)
    return Violation(
        rule_id=_RULE.rule_id,
        severity=_RULE.severity,
        location=f"{loc}:1",
        detail=(
            f"schema-bearing directory '{loc}' has no tests/ subdirectory — "
            f"add tests/ beside the schema"
        ),
        fix_hint_ref=getattr(_RULE, "fix_hint_ref", None),
    )


def find_missing_tests(dirs: Iterable[Path], *, root: Path) -> List[Violation]:
    """One violation per schema-bearing directory with no ``tests/`` child."""
    return [
        _missing_tests_violation(d, root=root)
        for d in dirs
        if not (d / "tests").is_dir()
    ]


def _scan_live() -> List[Violation]:
    out: List[Violation] = []
    for name in _ROOTS:
        out.extend(find_missing_tests(schema_bearing_dirs(REPO_ROOT / name), root=REPO_ROOT))
    return out


def test_contract_tests_subdirectory() -> None:
    """Live corpus: report every schema-bearing directory missing tests/."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=_scan_live())


# ---------------------------------------------------------------------------
# Detection proof
# ---------------------------------------------------------------------------
def test_missing_tests_dir_is_flagged(tmp_path: Path) -> None:
    d = tmp_path / "commons" / "coach"
    d.mkdir(parents=True)
    (d / "card.schema.json").write_text("{}", encoding="utf-8")
    v = find_missing_tests(schema_bearing_dirs(tmp_path), root=tmp_path)
    assert len(v) == 1 and "commons/coach" in v[0].detail, v


def test_present_tests_dir_passes(tmp_path: Path) -> None:
    d = tmp_path / "commons" / "coach"
    (d / "tests").mkdir(parents=True)
    (d / "card.schema.json").write_text("{}", encoding="utf-8")
    assert find_missing_tests(schema_bearing_dirs(tmp_path), root=tmp_path) == []


def test_dir_without_schemas_is_not_subject(tmp_path: Path) -> None:
    """A grouping directory that holds only subdirectories needs no tests/."""
    (tmp_path / "commons" / "coach").mkdir(parents=True)
    assert schema_bearing_dirs(tmp_path) == []


def test_tests_dir_itself_is_not_subject(tmp_path: Path) -> None:
    """Fixtures inside tests/ do not make tests/ a contract directory."""
    t = tmp_path / "commons" / "coach" / "tests"
    t.mkdir(parents=True)
    (t / "fixture.json").write_text("{}", encoding="utf-8")
    assert [d.name for d in schema_bearing_dirs(tmp_path)] == []


def test_missing_root_is_not_a_violation(tmp_path: Path) -> None:
    assert schema_bearing_dirs(tmp_path / "telemetry") == []
