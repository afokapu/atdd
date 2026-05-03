# URN: component:govern-lifecycle:enforce-train-has-rendered-content:train-renders-content-validator:python:integration
# Tested-By:
# - test:govern-lifecycle:enforce-train-has-rendered-content:C001-UNIT-001-analyzer-pass
# - test:govern-lifecycle:enforce-train-has-rendered-content:C001-UNIT-002-analyzer-empty
# - test:govern-lifecycle:enforce-train-has-rendered-content:C001-UNIT-003-analyzer-stub
# - test:govern-lifecycle:enforce-train-has-rendered-content:C001-UNIT-004-analyzer-error
# - test:train:0001-self-compliance-validate:E2E-001-train-renders-content-smoke
# Runtime: python
# Purpose: Behavioral validator — mount each train and assert the rendered DOM is non-empty and non-stub.

"""
Train-Renders-Content Validator (issue #335).

Behavioral peer to the source-inspection validators in this directory.
For every train registered in ``plan/_trains.yaml``, mount the train
through ``FrontendTrainRunner.runTrain`` in a headless harness and assert
the resulting DOM is non-empty and not a stub-only render.

Architecture (4-layer split):
- Entities: ``TrainRenderStatus``, ``TrainRenderHarnessResult``.
- Use case: ``TrainRenderAnalyzer`` — pure-Python classifier that turns a
  parsed harness result into a list of canonical ``Violation`` records.
- Integration: ``HarnessInvoker`` — subprocess bridge to
  ``.atdd/harness/mount-train.mjs`` (Node + @testing-library/preact).
  GREEN-phase deliverable.
- Tests: orchestration layer (pytest functions over fixtures + the
  opt-in repo-level audit gated by ``.atdd/config.yaml``).

Rule registry (declared in src/atdd/tester/conventions/smoke.convention.yaml
under ``behavioral_render.rules``; grammar in
src/atdd/coach/conventions/rule-id.convention.yaml):

  TESTER-RENDER-001 — empty render (textLength == 0, no expected_content
                      match), severity 4.
  TESTER-RENDER-002 — stub render (DOM is loader/skeleton/placeholder
                      only), severity 4.
  TESTER-RENDER-003 — harness error (subprocess crash, timeout, or
                      schema-invalid stdout), severity 3.

Phase: RED. The integration-layer ``HarnessInvoker`` and the use-case
``TrainRenderAnalyzer.classify`` raise ``NotImplementedError`` until
GREEN. The orchestration tests below therefore fail by design — that is
the RED contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.config import load_atdd_config
from atdd.coach.validators._violation import Violation


REPO_ROOT = find_repo_root()
FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "train_renders_content"

RULE_EMPTY_RENDER = "TESTER-RENDER-001"
RULE_STUB_RENDER = "TESTER-RENDER-002"
RULE_HARNESS_ERROR = "TESTER-RENDER-003"


# ============================================================================
# LAYER 1: ENTITIES
# ============================================================================


@dataclass(frozen=True)
class TrainRenderHarnessResult:
    """Parsed JSON produced by .atdd/harness/mount-train.mjs on stdout.

    Conforms to src/atdd/tester/schemas/train-render-harness-result.schema.json.
    """

    train_id: str
    text_length: int
    matched_expectations: List[str]
    stub_detected: bool
    stub_reason: Optional[str] = None
    error: Optional[str] = None
    duration_ms: int = 0

    @classmethod
    def from_dict(cls, data: dict) -> "TrainRenderHarnessResult":
        return cls(
            train_id=data["trainId"],
            text_length=int(data["textLength"]),
            matched_expectations=list(data.get("matchedExpectations", [])),
            stub_detected=bool(data["stubDetected"]),
            stub_reason=data.get("stubReason"),
            error=data.get("error"),
            duration_ms=int(data.get("durationMs", 0)),
        )


@dataclass
class TrainRenderStatus:
    """Render-content status for a single train after analysis."""

    train_id: str
    harness_result: Optional[TrainRenderHarnessResult] = None
    violations: List[Violation] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        return not self.violations


# ============================================================================
# LAYER 2: USE CASE
# ============================================================================


class TrainRenderAnalyzer:
    """Classify a harness result into canonical Violations.

    Pure-Python: no subprocess, no I/O. Drives both the fixture-driven unit
    tests and the orchestration-layer repo audit. Rule-id emission keeps
    parity with the issue body's reserved IDs and severities.
    """

    def __init__(self, repo_root: Path = REPO_ROOT) -> None:
        self.repo_root = repo_root

    def classify(self, result: TrainRenderHarnessResult) -> List[Violation]:
        """Return the list of Violations a single harness result triggers.

        RED-phase stub: raises NotImplementedError. GREEN delivers the
        classifier (empty / stub / error / clean → list[Violation]).
        """
        raise NotImplementedError(
            "TrainRenderAnalyzer.classify is delivered in GREEN — see issue #335 Phase 2."
        )


# ============================================================================
# LAYER 3: INTEGRATION
# ============================================================================


class HarnessInvoker:
    """Subprocess bridge to .atdd/harness/mount-train.mjs.

    Spawns Node with the per-repo harness templates (see
    src/atdd/coach/templates/harness/) and parses the JSON line printed
    on stdout. Hard 30 s timeout per train. Errors are surfaced as
    ``TrainRenderHarnessResult(error=...)`` — never silently swallowed
    (per #357).
    """

    DEFAULT_TIMEOUT_SECONDS: int = 30

    def __init__(self, repo_root: Path = REPO_ROOT) -> None:
        self.repo_root = repo_root

    def invoke(self, train_id: str) -> TrainRenderHarnessResult:
        """Run the harness for a single train and return the parsed result.

        RED-phase stub. GREEN implements ``subprocess.run`` against
        ``.atdd/harness/mount-train.mjs --train <train_id>`` with the
        timeout and JSON parse described above.
        """
        raise NotImplementedError(
            "HarnessInvoker.invoke is delivered in GREEN — see issue #335 Phase 2."
        )


# ============================================================================
# LAYER 4: TESTS (orchestration)
# ============================================================================


def _load_fixture(name: str) -> TrainRenderHarnessResult:
    raw = json.loads((FIXTURE_ROOT / name / "harness_output.json").read_text(encoding="utf-8"))
    return TrainRenderHarnessResult.from_dict(raw)


@pytest.mark.tester
def test_analyzer_pass_fixture_emits_no_violations():
    """Pass fixture: textLength > 0, no stub → zero Violations."""
    analyzer = TrainRenderAnalyzer(REPO_ROOT)
    result = _load_fixture("pass")

    violations = analyzer.classify(result)

    assert violations == [], f"expected zero violations, got {violations!r}"


@pytest.mark.tester
def test_analyzer_fail_empty_fixture_emits_render_001():
    """Empty fixture: textLength == 0 → exactly one TESTER-RENDER-001."""
    analyzer = TrainRenderAnalyzer(REPO_ROOT)
    result = _load_fixture("fail_empty")

    violations = analyzer.classify(result)

    assert len(violations) == 1, f"expected 1 violation, got {len(violations)}"
    v = violations[0]
    assert v.rule_id == RULE_EMPTY_RENDER
    assert v.severity == 4
    assert result.train_id in v.location


@pytest.mark.tester
def test_analyzer_fail_stub_fixture_emits_render_002():
    """Stub fixture: stubDetected == true → exactly one TESTER-RENDER-002."""
    analyzer = TrainRenderAnalyzer(REPO_ROOT)
    result = _load_fixture("fail_stub")

    violations = analyzer.classify(result)

    assert len(violations) == 1, f"expected 1 violation, got {len(violations)}"
    v = violations[0]
    assert v.rule_id == RULE_STUB_RENDER
    assert v.severity == 4
    if result.stub_reason:
        assert result.stub_reason in v.detail


@pytest.mark.tester
def test_analyzer_harness_error_fixture_emits_render_003():
    """Error fixture: harness failed → exactly one TESTER-RENDER-003."""
    analyzer = TrainRenderAnalyzer(REPO_ROOT)
    result = _load_fixture("harness_error")

    violations = analyzer.classify(result)

    assert len(violations) == 1, f"expected 1 violation, got {len(violations)}"
    v = violations[0]
    assert v.rule_id == RULE_HARNESS_ERROR
    assert v.severity == 3
    assert result.error and result.error in v.detail


@pytest.mark.tester
def test_violation_records_use_canonical_rule_ids():
    """All emitted violations must be canonical Violation records.

    Closes the substrate-compliance gap (#340): no legacy prose-string
    violations, no ad-hoc dataclasses.
    """
    analyzer = TrainRenderAnalyzer(REPO_ROOT)
    for fixture in ("fail_empty", "fail_stub", "harness_error"):
        result = _load_fixture(fixture)
        for v in analyzer.classify(result):
            assert isinstance(v, Violation), (
                f"{fixture}: expected Violation, got {type(v).__name__}"
            )
            assert v.rule_id.startswith("TESTER-RENDER-"), (
                f"{fixture}: rule_id {v.rule_id!r} does not match TESTER-RENDER-NNN"
            )


@pytest.mark.tester
def test_repo_train_renders_content(ratchet_baseline):
    """Mount every registered train and assert non-empty, non-stub DOM.

    Opt-in via ``.atdd/config.yaml → train_renders_content.enabled``
    (default false). When disabled — including the toolkit-self repo —
    the test skips so it never produces false positives in headless,
    no-frontend repos.
    """
    config = load_atdd_config(REPO_ROOT)
    cfg = (config or {}).get("train_renders_content", {}) or {}
    if not cfg.get("enabled", False):
        pytest.skip("train_renders_content.enabled is false; opt in via .atdd/config.yaml")

    # GREEN delivers the orchestration: discover trains via PlanTrainDiscovery,
    # fan out HarnessInvoker, classify with TrainRenderAnalyzer, then ratchet.
    raise NotImplementedError(
        "Repo audit orchestration is delivered in GREEN — see issue #335 Phase 2."
    )
