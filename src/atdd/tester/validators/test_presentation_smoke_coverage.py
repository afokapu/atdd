# URN: component:govern-lifecycle:smoke-substrate:PresentationSmokeCoverage:tester:application
# Runtime: python
# Purpose: Detect presentation-layer files in consumer repos that lack a matching
#          e2e/*smoke*.spec.ts file; emit ratcheted TESTER-SMOKE-PRES-001 violations.

"""
TESTER-SMOKE-PRES-001: Steady-state presentation→smoke coverage validator.

Walks ``web/src/*/presentation/*.tsx`` in the target repo and emits a
structured ``Violation`` for every presentation file that has no matching
``e2e/*smoke*.spec.ts``.

Distinct from sibling validators:
- ``test_smoke_coverage.py``: train-scoped, walks ``e2e/{train_id}/`` only.
- ``test_train_route_smoke_coverage.py``: train-route-scoped (parity with BE).
- ``test_presentation_ratchet_requires_smoke.py`` (#358, coder, COACH-RATCHET-PRES-001):
  detects ratchet-shrink events on presentation files.

This validator is steady-state: it fires whether or not the file changed,
catching regressions where a presentation file lands without any browser
verification (consumer-repo evidence: ``janetbusiness/jel-app#307``, ``#308``).

Severity 3 (architectural) per #340 + smoke.convention.yaml — advisory + gate,
not stop-the-world. Ratcheted via ``.atdd/baselines/tester.yaml``.

Conventions:
- src/atdd/tester/conventions/smoke.convention.yaml (validator declared)
- src/atdd/coach/conventions/rule-id.convention.yaml (TESTER domain, sev scale)
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.validators._violation import Violation
from atdd.coach.utils.disposition_gate import assert_disposition_satisfied


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Stable rule identity (issue #293 + #340 substrate)
RULE_ID = "tester.smoke.pres"
SEVERITY = 3  # architectural per rule-id.convention.yaml severity_scale

# Path conventions — consumer-repo layout (toolkit-self has no web/)
WEB_SRC_DIR = "web/src"
PRESENTATION_DIRNAME = "presentation"
PRESENTATION_GLOB = "*.tsx"
E2E_DIRNAME = "e2e"
SMOKE_SPEC_GLOB = "*.spec.ts"
SMOKE_TOKEN = "smoke"


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PresentationFile:
    """A presentation-layer source file in a consumer repo.

    ``wagon`` is the path segment between ``web/src/`` and ``presentation/``
    — e.g. ``web/src/match/presentation/Grid.tsx`` → wagon=``match``.
    """

    path: Path  # absolute
    rel_path: str  # POSIX, repo-root-relative
    wagon: str
    component: str  # basename without extension


@dataclass(frozen=True)
class SmokeSpec:
    """A Playwright smoke spec under ``e2e/``."""

    path: Path
    rel_path: str  # POSIX, repo-root-relative
    basename_lower: str


# ---------------------------------------------------------------------------
# Discovery
# ---------------------------------------------------------------------------


def find_presentation_files(repo_root: Path) -> List[PresentationFile]:
    """Walk ``web/src/*/presentation/*.tsx`` in *repo_root*.

    Returns an empty list when ``web/src/`` is absent (toolkit-self repo).
    """
    web_src = repo_root / WEB_SRC_DIR
    if not web_src.is_dir():
        return []
    out: List[PresentationFile] = []
    for tsx in sorted(web_src.glob(f"*/{PRESENTATION_DIRNAME}/{PRESENTATION_GLOB}")):
        try:
            rel = tsx.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = tsx.as_posix()
        # web/src/<wagon>/presentation/<Component>.tsx
        parts = tsx.relative_to(web_src).parts
        if len(parts) < 3 or parts[1] != PRESENTATION_DIRNAME:
            continue
        out.append(PresentationFile(
            path=tsx,
            rel_path=rel,
            wagon=parts[0],
            component=tsx.stem,
        ))
    return out


def find_smoke_specs(repo_root: Path) -> List[SmokeSpec]:
    """Walk ``e2e/`` for ``*smoke*.spec.ts`` files (any depth).

    Returns an empty list when ``e2e/`` is absent.
    """
    e2e_root = repo_root / E2E_DIRNAME
    if not e2e_root.is_dir():
        return []
    out: List[SmokeSpec] = []
    for spec in sorted(e2e_root.rglob(SMOKE_SPEC_GLOB)):
        if SMOKE_TOKEN not in spec.stem.lower():
            continue
        try:
            rel = spec.resolve().relative_to(repo_root.resolve()).as_posix()
        except ValueError:
            rel = spec.as_posix()
        out.append(SmokeSpec(
            path=spec,
            rel_path=rel,
            basename_lower=spec.stem.lower(),
        ))
    return out


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------


def _token_present(needle: str, haystack: str) -> bool:
    """True when *needle* appears as a kebab/snake/word-boundary token in *haystack*."""
    if not needle:
        return False
    return re.search(
        rf"(?:^|[^a-z0-9]){re.escape(needle.lower())}(?:[^a-z0-9]|$)",
        haystack.lower(),
    ) is not None


def smoke_spec_covers(spec: SmokeSpec, pres: PresentationFile) -> bool:
    """True when *spec* covers *pres* by wagon-name token match.

    Matching strategy (deliberately permissive to avoid false positives in
    consumer repos with idiosyncratic naming):
      - The spec's relative path (lowercased, separators normalized to ``-``)
        contains the presentation file's *wagon* as a token.

    Component-name matching is intentionally NOT required: a single
    ``smoke-match.spec.ts`` covers every presentation file under
    ``web/src/match/presentation/``. Granular per-component coverage is a
    future-tightening lever.
    """
    normalized = re.sub(r"[/_]", "-", spec.rel_path.lower())
    return _token_present(pres.wagon, normalized)


def is_covered(pres: PresentationFile, specs: Sequence[SmokeSpec]) -> bool:
    return any(smoke_spec_covers(s, pres) for s in specs)


# ---------------------------------------------------------------------------
# Rule emission
# ---------------------------------------------------------------------------


class PresentationSmokeRule:
    """Stable identity for TESTER-SMOKE-PRES-001."""

    RULE_ID = RULE_ID
    SEVERITY = SEVERITY

    @classmethod
    def violation_for(cls, pres: PresentationFile) -> Violation:
        return Violation(
            rule_id=cls.RULE_ID,
            severity=cls.SEVERITY,
            location=f"{pres.rel_path}:1",
            detail=(
                f"Presentation file has no matching e2e/*smoke*.spec.ts "
                f"(wagon={pres.wagon!r}); add a Playwright smoke spec or "
                f"name an existing one to include the wagon token."
            ),
        )

    @classmethod
    def violations_for(
        cls,
        presentation_files: Iterable[PresentationFile],
        specs: Sequence[SmokeSpec],
    ) -> List[Violation]:
        return [
            cls.violation_for(p)
            for p in presentation_files
            if not is_covered(p, specs)
        ]


# ---------------------------------------------------------------------------
# Repo-driven scan entrypoint
# ---------------------------------------------------------------------------


def scan_presentation_smoke_coverage(
    repo_root: Path,
) -> Tuple[int, List[Violation]]:
    """Scan *repo_root* and return ``(count, violations)`` for the ratchet.

    On the toolkit-self repo (no ``web/src/``) this returns ``(0, [])``.
    """
    presentation_files = find_presentation_files(repo_root)
    if not presentation_files:
        return 0, []
    specs = find_smoke_specs(repo_root)
    violations = PresentationSmokeRule.violations_for(presentation_files, specs)
    return len(violations), violations


# ---------------------------------------------------------------------------
# Unit tests — pure logic (no real repo state)
# ---------------------------------------------------------------------------


def _seed_pres(tmp_path: Path, wagon: str, component: str) -> Path:
    target = tmp_path / WEB_SRC_DIR / wagon / PRESENTATION_DIRNAME / f"{component}.tsx"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("export default function X() { return null }\n")
    return target


def _seed_smoke(tmp_path: Path, name: str) -> Path:
    target = tmp_path / E2E_DIRNAME / f"{name}.spec.ts"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("import { test } from '@playwright/test'; test('x', () => {})\n")
    return target


@pytest.mark.tester
def test_rule_id_and_severity_are_documented_constants():
    assert PresentationSmokeRule.RULE_ID == "TESTER-SMOKE-PRES-001"
    assert PresentationSmokeRule.SEVERITY == 3


@pytest.mark.tester
def test_finds_presentation_tsx_under_web_src(tmp_path):
    _seed_pres(tmp_path, "match", "Grid")
    _seed_pres(tmp_path, "onboarding", "Login")
    out = find_presentation_files(tmp_path)
    assert {p.wagon for p in out} == {"match", "onboarding"}
    assert {p.component for p in out} == {"Grid", "Login"}


@pytest.mark.tester
def test_returns_empty_when_web_src_missing(tmp_path):
    """Toolkit-self has no web/ — must return cleanly."""
    assert find_presentation_files(tmp_path) == []


@pytest.mark.tester
def test_skips_components_directory_under_wagon(tmp_path):
    """Only files under */presentation/ qualify; components/ is out of scope."""
    target = tmp_path / WEB_SRC_DIR / "match" / "components" / "Button.tsx"
    target.parent.mkdir(parents=True)
    target.write_text("export default function B() { return null }\n")
    assert find_presentation_files(tmp_path) == []


@pytest.mark.tester
def test_finds_smoke_spec_files_under_e2e(tmp_path):
    """Only spec files whose stem contains the smoke token qualify."""
    _seed_smoke(tmp_path, "smoke-match-grid")
    _seed_smoke(tmp_path, "regression")  # missing the smoke token → ignored
    specs = find_smoke_specs(tmp_path)
    assert {s.path.name for s in specs} == {"smoke-match-grid.spec.ts"}


@pytest.mark.tester
def test_smoke_spec_covers_by_wagon_token(tmp_path):
    pres = PresentationFile(
        path=tmp_path / "x.tsx",
        rel_path="web/src/match/presentation/Grid.tsx",
        wagon="match",
        component="Grid",
    )
    spec = SmokeSpec(
        path=tmp_path / "y.spec.ts",
        rel_path="e2e/smoke-match-grid.spec.ts",
        basename_lower="smoke-match-grid",
    )
    assert smoke_spec_covers(spec, pres) is True


@pytest.mark.tester
def test_smoke_spec_does_not_cover_unrelated_wagon():
    pres = PresentationFile(
        path=Path("p"),
        rel_path="web/src/match/presentation/Grid.tsx",
        wagon="match",
        component="Grid",
    )
    spec = SmokeSpec(
        path=Path("s"),
        rel_path="e2e/smoke-onboarding-login.spec.ts",
        basename_lower="smoke-onboarding-login",
    )
    assert smoke_spec_covers(spec, pres) is False


@pytest.mark.tester
def test_wagon_token_match_respects_word_boundaries():
    """'match' must not match 'watchmaker' (substring trap)."""
    pres = PresentationFile(
        path=Path("p"),
        rel_path="web/src/match/presentation/Grid.tsx",
        wagon="match",
        component="Grid",
    )
    spec = SmokeSpec(
        path=Path("s"),
        rel_path="e2e/smoke-watchmaker.spec.ts",
        basename_lower="smoke-watchmaker",
    )
    assert smoke_spec_covers(spec, pres) is False


@pytest.mark.tester
def test_is_covered_true_when_any_spec_matches():
    pres = PresentationFile(
        path=Path("p"),
        rel_path="web/src/match/presentation/Grid.tsx",
        wagon="match",
        component="Grid",
    )
    specs = [
        SmokeSpec(Path("s1"), "e2e/smoke-onboarding.spec.ts", "smoke-onboarding"),
        SmokeSpec(Path("s2"), "e2e/smoke-match.spec.ts", "smoke-match"),
    ]
    assert is_covered(pres, specs) is True


@pytest.mark.tester
def test_is_covered_false_when_no_spec_matches():
    pres = PresentationFile(
        path=Path("p"),
        rel_path="web/src/match/presentation/Grid.tsx",
        wagon="match",
        component="Grid",
    )
    specs = [
        SmokeSpec(Path("s"), "e2e/smoke-onboarding.spec.ts", "smoke-onboarding"),
    ]
    assert is_covered(pres, specs) is False


@pytest.mark.tester
def test_violation_for_carries_rule_id_and_location():
    pres = PresentationFile(
        path=Path("p"),
        rel_path="web/src/match/presentation/Grid.tsx",
        wagon="match",
        component="Grid",
    )
    v = PresentationSmokeRule.violation_for(pres)
    assert isinstance(v, Violation)
    assert v.rule_id == "TESTER-SMOKE-PRES-001"
    assert v.severity == 3
    assert v.location == "web/src/match/presentation/Grid.tsx:1"
    assert "match" in v.detail


@pytest.mark.tester
def test_violations_for_emits_only_uncovered():
    pres_a = PresentationFile(Path("a"), "web/src/match/presentation/Grid.tsx", "match", "Grid")
    pres_b = PresentationFile(Path("b"), "web/src/onboarding/presentation/Login.tsx", "onboarding", "Login")
    specs = [SmokeSpec(Path("s"), "e2e/smoke-match.spec.ts", "smoke-match")]

    violations = PresentationSmokeRule.violations_for([pres_a, pres_b], specs)
    assert len(violations) == 1
    assert "onboarding" in violations[0].detail


@pytest.mark.tester
def test_scan_returns_zero_when_no_presentation_files(tmp_path):
    """Toolkit-self repo (no web/) returns clean."""
    count, violations = scan_presentation_smoke_coverage(tmp_path)
    assert count == 0
    assert violations == []


@pytest.mark.tester
def test_scan_flags_uncovered_presentation_file(tmp_path):
    _seed_pres(tmp_path, "match", "Grid")  # no smoke spec
    count, violations = scan_presentation_smoke_coverage(tmp_path)
    assert count == 1
    assert violations[0].rule_id == "TESTER-SMOKE-PRES-001"
    assert "match" in violations[0].detail


@pytest.mark.tester
def test_scan_skips_presentation_when_smoke_spec_present(tmp_path):
    _seed_pres(tmp_path, "match", "Grid")
    _seed_smoke(tmp_path, "smoke-match")
    count, violations = scan_presentation_smoke_coverage(tmp_path)
    assert count == 0
    assert violations == []


# ---------------------------------------------------------------------------
# Integration test (ratcheted)
# ---------------------------------------------------------------------------


@pytest.mark.tester
def test_presentation_smoke_coverage():
    """
    TESTER-SMOKE-PRES-001: every web/src/*/presentation/*.tsx must have a
    matching e2e/*smoke*.spec.ts.

    Toolkit-self repo has no web/ — this integration test naturally returns
    a clean count of 0. Consumer repos exercise the regression path.

    Ratchet baseline: existing gaps baselined in .atdd/baselines/tester.yaml,
    new presentation files without smoke fail as regressions.
    """
    repo_root = find_repo_root()
    count, violations = scan_presentation_smoke_coverage(repo_root)
    assert_disposition_satisfied(
        validator_id="presentation_smoke_coverage",
        violations=violations,
    )
