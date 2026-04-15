"""
Test that every wagon's trains.ts exposes the required presentation export
symbols the FrontendTrainRunner needs to register the wagon.

Validates:
- SPEC-CODER-TRAIN-0002: For each wagon directory matching wagon_glob, the
  adjacent trains.ts file must exist and export every name in required_exports.

Skips cleanly when .atdd/config.yaml has no wagon_trains_export_shape key.

Convention: src/atdd/coder/conventions/frontend.convention.yaml → train_composition
Config: .atdd/config.yaml → wagon_trains_export_shape
"""

import re
from pathlib import Path
from typing import Dict, List, Set

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import load_atdd_config


REPO_ROOT = find_repo_root()


_NAMED_EXPORT_RE = re.compile(
    r"""export\s+(?:const|let|var|function|class|async\s+function)\s+(?P<name>[A-Za-z_][\w]*)"""
)

_EXPORT_LIST_RE = re.compile(
    r"""export\s*\{(?P<body>[^}]*)\}"""
)

_EXPORT_ITEM_RE = re.compile(
    r"""(?P<name>[A-Za-z_][\w]*)(?:\s+as\s+(?P<alias>[A-Za-z_][\w]*))?"""
)


def _extract_exports(source: str) -> Set[str]:
    """Return the set of names exported from a TypeScript source string.

    Handles:
      - ``export const|let|var|function|class <name> ...``
      - ``export { a, b as c, d }``
      - ``export async function <name> ...``

    Does not handle re-exports (``export * from ...``) or default exports
    — the former are opaque without resolving the target module, and the
    latter are anonymous, so neither can satisfy a named-export contract.
    """
    names: Set[str] = set()

    for match in _NAMED_EXPORT_RE.finditer(source):
        names.add(match.group("name"))

    for match in _EXPORT_LIST_RE.finditer(source):
        body = match.group("body")
        for item in body.split(","):
            item = item.strip()
            if not item:
                continue
            m = _EXPORT_ITEM_RE.match(item)
            if not m:
                continue
            exported_name = m.group("alias") or m.group("name")
            names.add(exported_name)

    return names


def _analyze_wagon_trains(
    wagon_dir: Path,
    required_exports: List[str],
) -> List[str]:
    """Return SPEC-CODER-TRAIN-0002 violation strings for one wagon directory.

    A wagon that has no ``trains.ts`` at all is a hard failure — every wagon
    is expected to register at least one presentation, so the absence of the
    file means the wagon cannot participate in any train.
    """
    violations: List[str] = []
    trains_file = wagon_dir / "trains.ts"
    rel = wagon_dir.name

    if not trains_file.exists():
        violations.append(
            f"  SPEC-CODER-TRAIN-0002 FAIL: wagon missing trains.ts\n"
            f"    Wagon:     {rel}\n"
            f"    Expected:  {trains_file}\n"
            f"    Fix:       Create trains.ts and export {required_exports}"
        )
        return violations

    try:
        source = trains_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        violations.append(
            f"  SPEC-CODER-TRAIN-0002 FAIL: trains.ts unreadable\n"
            f"    Path:      {trains_file}\n"
            f"    Error:     {exc}"
        )
        return violations

    exports = _extract_exports(source)
    missing = [name for name in required_exports if name not in exports]

    if missing:
        violations.append(
            f"  SPEC-CODER-TRAIN-0002 FAIL: wagon trains.ts missing required exports\n"
            f"    Wagon:     {rel}\n"
            f"    File:      {trains_file}\n"
            f"    Missing:   {missing}\n"
            f"    Found:     {sorted(exports)}\n"
            f"    Fix:       Export every name in required_exports"
        )

    return violations


def _load_export_shape_config() -> Dict:
    config = load_atdd_config(REPO_ROOT)
    return config.get("wagon_trains_export_shape", {}) or {}


@pytest.mark.coder
def test_wagon_trains_export_shape_matches_contract():
    """SPEC-CODER-TRAIN-0002: Every wagon directory matching wagon_glob must
    have a trains.ts file exporting every name in required_exports.

    Given: .atdd/config.yaml contains a wagon_trains_export_shape block
    When:  The validator globs wagon directories and parses each trains.ts
    Then:  Missing files or missing exports are hard failures; absent
           configuration is a clean skip.
    """
    cfg = _load_export_shape_config()

    if not cfg or cfg.get("enabled") is False:
        pytest.skip(
            "wagon_trains_export_shape not configured in .atdd/config.yaml "
            "(opt-in per SPEC-CODER-TRAIN-0002)"
        )

    wagon_glob = cfg.get("wagon_glob")
    required_exports = cfg.get("required_exports", [])

    if not wagon_glob or not required_exports:
        pytest.fail(
            "SPEC-CODER-TRAIN-0002 FAIL: wagon_trains_export_shape missing "
            "required keys wagon_glob and required_exports"
        )

    wagon_dirs = sorted(
        match for match in REPO_ROOT.glob(wagon_glob) if match.is_dir()
    )

    if not wagon_dirs:
        pytest.skip(
            f"No wagon directories matched wagon_glob={wagon_glob!r}. "
            "Add wagons or update the glob."
        )

    violations: List[str] = []
    for wagon_dir in wagon_dirs:
        violations.extend(_analyze_wagon_trains(wagon_dir, required_exports))

    if violations:
        pytest.fail(
            f"\n\n{len(violations)} wagon(s) violate trains.ts export shape:\n\n"
            + "\n\n".join(violations)
        )


# ---------------------------------------------------------------------------
# Unit tests for the pure helpers (run in every mode, no config required).
# ---------------------------------------------------------------------------


_TRAINS_TS_POSITIVE = """
import type { FC } from 'preact/compat';

export const HomeTrainView: FC<TrainProps> = (props) => {
  return <div>home</div>;
};

export function runTrainStep(cargo: Cargo) {
  return cargo;
}

export { ProfileTrainView } from './profile-view';
""".strip()


_TRAINS_TS_PARTIAL = """
export function runTrainStep(cargo: Cargo) {
  return cargo;
}
""".strip()


def test_extract_exports_finds_const_function_and_list_forms():
    """Extractor finds ``export const``, ``export function``, and ``export { X }``."""
    exports = _extract_exports(_TRAINS_TS_POSITIVE)
    assert "HomeTrainView" in exports
    assert "runTrainStep" in exports
    assert "ProfileTrainView" in exports


def test_extract_exports_returns_empty_for_plain_source():
    """Extractor returns empty set when no exports are declared."""
    exports = _extract_exports("const internal = 42;\nfunction helper() {}\n")
    assert exports == set()


def test_analyze_wagon_reports_missing_trains_file(tmp_path):
    """A wagon without trains.ts fails hard."""
    (tmp_path / "empty-wagon").mkdir()
    violations = _analyze_wagon_trains(
        tmp_path / "empty-wagon",
        required_exports=["HomeTrainView", "runTrainStep"],
    )
    assert len(violations) == 1
    assert "missing trains.ts" in violations[0]


def test_analyze_wagon_reports_partial_exports(tmp_path):
    """A wagon whose trains.ts is missing some required exports fails hard."""
    wagon = tmp_path / "partial-wagon"
    wagon.mkdir()
    (wagon / "trains.ts").write_text(_TRAINS_TS_PARTIAL, encoding="utf-8")

    violations = _analyze_wagon_trains(
        wagon,
        required_exports=["HomeTrainView", "runTrainStep"],
    )
    assert len(violations) == 1
    message = violations[0]
    assert "missing required exports" in message
    assert "HomeTrainView" in message
    assert "runTrainStep" not in message.split("Missing:")[1].split("Found")[0]


def test_analyze_wagon_passes_when_contract_satisfied(tmp_path):
    """A wagon whose trains.ts exports all required names passes."""
    wagon = tmp_path / "full-wagon"
    wagon.mkdir()
    (wagon / "trains.ts").write_text(_TRAINS_TS_POSITIVE, encoding="utf-8")

    violations = _analyze_wagon_trains(
        wagon,
        required_exports=["HomeTrainView", "runTrainStep", "ProfileTrainView"],
    )
    assert violations == []
