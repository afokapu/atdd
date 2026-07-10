# Phase: GREEN
# Layer: backend.domain
"""
Synthetic-fixture anti-pattern scan helpers (issue #855, extracted #1385).

Scans SMOKE-phase test files referenced by WMBT YAML acceptances and emits
Violations for three synthetic-fixture anti-patterns:

  1. FakeMultiplexer import or instantiation
  2. subprocess.Popen with a cat/sleep/python stub as the primary agent command
  3. _SYNTHETIC_AGENT module-level constant (embedded Python script)

Rule: ``planner.smoke.synthetic-fixture-bypass`` (severity 3)
Convention: src/atdd/tester/conventions/smoke.convention.yaml::synthetic_fixture_anti_patterns

Also provides ``walk_all_smoke_acceptances_for_anti_patterns`` for the L002 meta-walker.

Enforcement lives in the convention variant
``validators/conventions/policy/test_smoke_synthetic_fixture_bypass.py``; this module
holds the scan helpers so they outlive the retired legacy validator (#1207 sweep).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple

import yaml

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

_RULE_ID = "planner.smoke.synthetic-fixture-bypass"
_RULE = bind_rule("planner.smoke.synthetic-fixture-bypass")
_SEVERITY = 3

REPO_ROOT = find_repo_root()
PLAN_DIR = REPO_ROOT / "plan"

_WMBT_FILENAME_RE = re.compile(r"^[DLPCEMYRK]\d{3}\.yaml$")
_SMOKE_URN_RE = re.compile(
    r"^acc:[a-z][a-z0-9-]*:[DLPCEMYRK]\d{3}-SMOKE-\d{3}(?:-[a-z0-9-]+)?$"
)
_STUB_COMMANDS = ("cat", "sleep", "python")
_FAKE_MUX_PATTERN = re.compile(r"FakeMultiplexer")
_SYNTHETIC_AGENT_PATTERN = re.compile(r"_SYNTHETIC_AGENT\s*=")
_STUB_POPEN_PATTERN = re.compile(
    r"""[Pp]open\s*\(\s*[\[\(]["'](?:""" + "|".join(_STUB_COMMANDS) + r""")["']"""
)
# Inline suppression: # atdd:suppress(planner.smoke.synthetic-fixture-bypass) UNTIL=YYYY-MM-DD
_SUPPRESS_PATTERN = re.compile(
    r"#\s*atdd:suppress\(planner\.smoke\.synthetic-fixture-bypass\)"
)


def _is_smoke_acceptance(identity: Dict[str, Any]) -> bool:
    urn = identity.get("urn", "")
    phase = identity.get("phase", "")
    return phase == "SMOKE" or bool(_SMOKE_URN_RE.match(urn))


def _scan_file_for_violations(test_file: Path, acceptance_urn: str) -> List[Violation]:
    """Return Violations for synthetic-fixture patterns found in *test_file*."""
    if not test_file.exists():
        return []

    content = test_file.read_text(encoding="utf-8", errors="replace")

    # Honor inline suppression marker
    if _SUPPRESS_PATTERN.search(content):
        return []

    location = str(test_file)
    violations: List[Violation] = []

    if _FAKE_MUX_PATTERN.search(content):
        violations.append(Violation(
            rule_id=_RULE_ID,
            severity=_SEVERITY,
            location=f"{location}:1",
            detail=(
                f"FakeMultiplexer found in SMOKE test for {acceptance_urn}. "
                "SMOKE tests must drive the real CLI entry point (atdd spawn), "
                "not a synthetic multiplexer that bypasses production wiring."
            ),
        ))

    stub_match = _STUB_POPEN_PATTERN.search(content)
    if stub_match:
        stub_name = "stub"
        for cmd in _STUB_COMMANDS:
            if cmd in stub_match.group():
                stub_name = cmd
                break
        violations.append(Violation(
            rule_id=_RULE_ID,
            severity=_SEVERITY,
            location=f"{location}:1",
            detail=(
                f"subprocess.Popen with stub command '{stub_name}' found in "
                f"SMOKE test for {acceptance_urn}. "
                "SMOKE tests must drive the real atdd spawn path, not a "
                "cat/sleep/python stub."
            ),
        ))

    if _SYNTHETIC_AGENT_PATTERN.search(content):
        violations.append(Violation(
            rule_id=_RULE_ID,
            severity=_SEVERITY,
            location=f"{location}:1",
            detail=(
                f"_SYNTHETIC_AGENT constant found in SMOKE test for {acceptance_urn}. "
                "Embedded Python script constants bypass the real adapter command "
                "construction path. Write agent scripts to tmp_path files instead."
            ),
        ))

    return violations


def _resolve_test_file_from_urn(urn: str, repo_root: Path) -> Optional[Path]:
    """Search *repo_root* for a test file matching the acceptance URN slug."""
    parts = urn.split(":")
    if len(parts) < 3:
        return None
    id_part = parts[2]
    segments = id_part.split("-")
    if len(segments) < 3:
        return None
    prefix = f"test_{segments[0].lower()}_{segments[1].lower()}_{segments[2]}"
    for candidate in repo_root.rglob(f"{prefix}*.py"):
        if candidate.name.startswith(prefix):
            return candidate
    return None


def scan_for_synthetic_fixture_bypass(
    wmbt_files: Iterable[Path],
    repo_root: Path,
    resolve_test_file: Optional[Callable[[str], Optional[Path]]] = None,
) -> List[Violation]:
    """Scan SMOKE acceptances in *wmbt_files* for synthetic-fixture anti-patterns.

    Args:
        wmbt_files: WMBT YAML file paths.
        repo_root: Repository root for default test-file resolution.
        resolve_test_file: Optional ``(urn) -> Path | None``. When None, uses
            the built-in URN-to-filename resolver against *repo_root*.

    Returns:
        List of Violations; empty if no anti-patterns detected.
    """
    violations: List[Violation] = []
    for wmbt_file in wmbt_files:
        try:
            raw = yaml.safe_load(wmbt_file.read_text())
        except Exception:
            continue
        if not isinstance(raw, dict):
            continue
        for acc in raw.get("acceptances", []):
            identity = acc.get("identity", {})
            if not _is_smoke_acceptance(identity):
                continue
            urn = identity.get("urn", "")
            if not urn:
                continue
            if resolve_test_file is not None:
                test_file = resolve_test_file(urn)
            else:
                test_file = _resolve_test_file_from_urn(urn, repo_root)
            if test_file is None:
                continue
            violations.extend(_scan_file_for_violations(test_file, urn))
    return violations


def _iter_wmbt_files(plan_dir: Path) -> List[Path]:
    """Walk *plan_dir* and return all WMBT YAML files."""
    files: List[Path] = []
    if not plan_dir.is_dir():
        return files
    for child in plan_dir.iterdir():
        if child.is_dir():
            for f in child.glob("*.yaml"):
                if _WMBT_FILENAME_RE.match(f.name):
                    files.append(f)
        elif _WMBT_FILENAME_RE.match(child.name):
            files.append(child)
    return files


def _extract_urn_from_violation(violation: Violation) -> str:
    """Extract acceptance URN from the standard violation detail format."""
    detail = violation.detail
    if " for " in detail:
        after_for = detail.split(" for ")[1]
        candidate = after_for.split(".")[0].strip()
        if candidate.startswith("acc:"):
            return candidate
    return ""


def walk_all_smoke_acceptances_for_anti_patterns(
    plan_dir: Path,
    resolve_test_file: Optional[Callable[[str], Optional[Path]]] = None,
) -> List[Tuple[str, str]]:
    """Walk every WMBT YAML under *plan_dir* and return anti-pattern hits.

    Args:
        plan_dir: Plan directory (contains wagon subdirs with WMBT YAML files).
        resolve_test_file: Optional ``(urn) -> Path | None``.

    Returns:
        List of ``(acceptance_urn, hit_description)`` tuples. Empty when clean.
    """
    wmbt_files = _iter_wmbt_files(plan_dir)
    repo_root = plan_dir.parent if resolve_test_file is None else plan_dir
    violations = scan_for_synthetic_fixture_bypass(
        wmbt_files=wmbt_files,
        repo_root=repo_root,
        resolve_test_file=resolve_test_file,
    )
    return [(_extract_urn_from_violation(v) or v.location, v.detail) for v in violations]


# ---------------------------------------------------------------------------
# Pytest validator test (run by ``atdd validate planner``)
# ---------------------------------------------------------------------------
