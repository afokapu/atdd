# URN: acc:review-phase-boundaries:D003-UNIT-001-five-phase-prompts-committed
# Acceptance: AC-UNIT-001, AC-UNIT-002, AC-UNIT-003
# WMBT: wmbt:review-phase-boundaries:D003
# Phase: GREEN
# Layer: validator

"""Per-phase reviewer prompt template validation.

Validates the three WMBT D003 acceptances for issue #528:
  AC-UNIT-001 — five YAML files exist, parse, and declare persona+phase.
  AC-UNIT-002 — per-phase focus content matches spec §6.3.
  AC-UNIT-003 — rule-resolution block from spec §7.2 is embedded in each.
"""

import yaml
import pytest
from pathlib import Path

import atdd

_PKG_DIR = Path(atdd.__file__).resolve().parent
_REVIEWER_DIR = _PKG_DIR / "coach" / "prompts" / "persona" / "reviewer"

PHASE_FILES = (
    ("planned", "PLANNED"),
    ("red", "RED"),
    ("green", "GREEN"),
    ("smoke", "SMOKE"),
    ("refactor", "REFACTOR"),
)

# Per-phase focus markers from spec §6.3 table.
PHASE_FOCUS = {
    "PLANNED": [
        "WMBT",
        "acceptance",
        "dependenc",
    ],
    "RED": [
        "WMBT",
        "coverage",
        "right reason",
    ],
    "GREEN": [
        "AC coverage",
        "diff scope",
        "WMBT",
    ],
    "SMOKE": [
        "real infrastructure",
        "flakiness",
    ],
    "REFACTOR": [
        "semantics",
        "regression",
        "architectur",
    ],
}

# Rule-resolution block markers from spec §7.2.
RULE_RESOLUTION_MARKERS = [
    "rules_in_scope",
    "most specific",
    "rule_id: null",
    "legacy_alias",
    "SPEC-COACH-RULEID-0003",
    "severity",
]


def _load_prompt(slug: str) -> dict:
    path = _REVIEWER_DIR / f"{slug}.prompt.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# AC-UNIT-001: five files exist, valid YAML, persona + phase fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug,phase", PHASE_FILES)
def test_prompt_file_exists(slug: str, phase: str) -> None:
    """Each per-phase reviewer prompt file exists."""
    path = _REVIEWER_DIR / f"{slug}.prompt.yaml"
    assert path.exists(), f"Missing reviewer prompt: {path}"


@pytest.mark.parametrize("slug,phase", PHASE_FILES)
def test_prompt_parses_as_yaml(slug: str, phase: str) -> None:
    """Each prompt file parses as valid YAML."""
    data = _load_prompt(slug)
    assert isinstance(data, dict), f"{slug}.prompt.yaml did not parse to a dict"


@pytest.mark.parametrize("slug,phase", PHASE_FILES)
def test_prompt_declares_persona_reviewer(slug: str, phase: str) -> None:
    """Each prompt declares persona: reviewer."""
    data = _load_prompt(slug)
    assert data.get("persona") == "reviewer", (
        f"{slug}.prompt.yaml: expected persona=reviewer, got {data.get('persona')}"
    )


@pytest.mark.parametrize("slug,phase", PHASE_FILES)
def test_prompt_declares_phase_matching_filename(slug: str, phase: str) -> None:
    """Each prompt's phase field matches its filename (uppercase)."""
    data = _load_prompt(slug)
    assert data.get("phase") == phase, (
        f"{slug}.prompt.yaml: expected phase={phase}, got {data.get('phase')}"
    )


def test_exactly_five_prompt_files() -> None:
    """Exactly five YAML files exist in the reviewer prompts directory."""
    assert _REVIEWER_DIR.is_dir(), f"Directory missing: {_REVIEWER_DIR}"
    files = sorted(_REVIEWER_DIR.glob("*.prompt.yaml"))
    names = [f.name for f in files]
    expected = sorted(f"{slug}.prompt.yaml" for slug, _ in PHASE_FILES)
    assert names == expected, (
        f"Expected {expected}, got {names}"
    )


# ---------------------------------------------------------------------------
# AC-UNIT-002: per-phase focus matches spec §6.3
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug,phase", PHASE_FILES)
def test_prompt_contains_phase_focus_markers(slug: str, phase: str) -> None:
    """Each prompt body contains the focus markers for its phase (spec §6.3)."""
    data = _load_prompt(slug)
    body = str(data.get("prompt", ""))
    missing = [m for m in PHASE_FOCUS[phase] if m.lower() not in body.lower()]
    assert not missing, (
        f"{slug}.prompt.yaml: missing focus markers for {phase}: {missing}"
    )


# ---------------------------------------------------------------------------
# AC-UNIT-003: rule-resolution block embedded (spec §7.2)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("slug,phase", PHASE_FILES)
def test_prompt_contains_rule_resolution_block(slug: str, phase: str) -> None:
    """Each prompt embeds the rule_id_resolution block from spec §7.2."""
    data = _load_prompt(slug)
    block = str(data.get("rule_id_resolution", ""))
    missing = [m for m in RULE_RESOLUTION_MARKERS if m.lower() not in block.lower()]
    assert not missing, (
        f"{slug}.prompt.yaml: missing rule-resolution markers: {missing}"
    )


@pytest.mark.parametrize("slug,phase", PHASE_FILES)
def test_prompt_references_review_report_schema(slug: str, phase: str) -> None:
    """Each prompt references review-report.schema.json as the output contract."""
    data = _load_prompt(slug)
    body = str(data.get("prompt", ""))
    assert "review-report.schema.json" in body, (
        f"{slug}.prompt.yaml: must reference review-report.schema.json"
    )


@pytest.mark.parametrize("slug,phase", PHASE_FILES)
def test_prompt_references_atdd_agent_review(slug: str, phase: str) -> None:
    """Each prompt references the atdd agent review command as the output channel."""
    data = _load_prompt(slug)
    body = str(data.get("prompt", ""))
    assert "atdd agent review" in body, (
        f"{slug}.prompt.yaml: must reference 'atdd agent review'"
    )
