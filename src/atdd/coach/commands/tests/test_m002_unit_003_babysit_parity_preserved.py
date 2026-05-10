# URN: test:observe-and-correct:observer-runtime-and-rules:M002-UNIT-003-babysit-parity-preserved
# Acceptance: acc:observe-and-correct:M002-UNIT-003-babysit-parity-preserved
# WMBT: wmbt:observe-and-correct:M002
# Phase: GREEN
# Layer: application
"""M002-UNIT-003 — The absorbed functions `load_token_alert_threshold`,
`read_token_count`, `check_token_threshold` preserve babysit's existing
behavior verbatim — same firing decision for the same inputs.

Issue #507 (L3). Spec: `atdd-coach-spec-v9.md` §0.2 (absorption inventory),
§8.3 (rule 06).

Parity contract: for every fixture (token_count, threshold), babysit's
and the absorbed observer's `check_token_threshold` agree on whether the
alert fires. The default 400k threshold is preserved. The absorbed module
path is documented and discoverable from the rule YAML.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Module surface — absorbed functions live in coach/commands/token_threshold.py
# ---------------------------------------------------------------------------


def test_absorbed_module_exposes_three_functions():
    from atdd.coach.commands import token_threshold

    for name in (
        "load_token_alert_threshold",
        "read_token_count",
        "check_token_threshold",
        "DEFAULT_TOKEN_ALERT_THRESHOLD",
    ):
        assert hasattr(token_threshold, name), (
            f"missing absorbed symbol token_threshold.{name}"
        )


def test_default_threshold_preserved_at_400k():
    """The default 400k threshold MUST be preserved per spec §10."""
    from atdd.coach.commands.token_threshold import DEFAULT_TOKEN_ALERT_THRESHOLD

    assert DEFAULT_TOKEN_ALERT_THRESHOLD == 400_000


# ---------------------------------------------------------------------------
# Parity fixtures — above / at / below the default threshold
# ---------------------------------------------------------------------------

PARITY_FIXTURES: list[tuple[int | None, int, bool]] = [
    # (token_count, threshold, expected_fires)
    (None, 400_000, False),  # unknown count → no alert
    (0, 400_000, False),
    (100_000, 400_000, False),
    (399_999, 400_000, False),  # just below
    (400_000, 400_000, True),  # exactly at threshold fires (parity with babysit)
    (400_001, 400_000, True),  # just above
    (450_000, 400_000, True),
    (1_000_000, 400_000, True),
    # custom thresholds (config override)
    (340_000, 350_000, False),
    (349_999, 350_000, False),
    (350_000, 350_000, True),
    (360_000, 350_000, True),
]


@pytest.mark.parametrize("token_count,threshold,expected_fires", PARITY_FIXTURES)
def test_observer_check_token_threshold_matches_fixture(
    token_count: int | None, threshold: int, expected_fires: bool
):
    from atdd.coach.commands.token_threshold import check_token_threshold

    fired = check_token_threshold(
        token_count=token_count, threshold=threshold
    )
    assert bool(fired) is expected_fires, (
        f"observer check_token_threshold({token_count}, {threshold}) "
        f"expected fires={expected_fires}, got {fired!r}"
    )


@pytest.mark.parametrize("token_count,threshold,expected_fires", PARITY_FIXTURES)
def test_babysit_check_token_threshold_matches_fixture(
    token_count: int | None, threshold: int, expected_fires: bool
):
    """Babysit's `check_token_threshold` MUST agree on firing for every fixture.

    Babysit returns Optional[BabysitDecision] — None means no fire,
    a BabysitDecision means fire. Truthiness gives the firing decision.
    """
    from atdd.coach.commands.babysit import check_token_threshold

    decision = check_token_threshold(
        token_count=token_count, threshold=threshold
    )
    assert (decision is not None) is expected_fires, (
        f"babysit check_token_threshold({token_count}, {threshold}) "
        f"expected fires={expected_fires}, got {decision!r}"
    )


@pytest.mark.parametrize("token_count,threshold,expected_fires", PARITY_FIXTURES)
def test_observer_and_babysit_agree_on_firing(
    token_count: int | None, threshold: int, expected_fires: bool
):
    """The two implementations MUST agree on every parity fixture."""
    from atdd.coach.commands.babysit import (
        check_token_threshold as babysit_check,
    )
    from atdd.coach.commands.token_threshold import (
        check_token_threshold as observer_check,
    )

    babysit_fires = babysit_check(token_count=token_count, threshold=threshold) is not None
    observer_fires = bool(observer_check(token_count=token_count, threshold=threshold))

    assert babysit_fires == observer_fires == expected_fires, (
        f"parity break at ({token_count}, {threshold}): "
        f"babysit_fires={babysit_fires}, observer_fires={observer_fires}, "
        f"expected={expected_fires}"
    )


# ---------------------------------------------------------------------------
# Discoverability: absorbed_module path documented in rule YAML (AC-UNIT-003)
# ---------------------------------------------------------------------------


def test_rule_yaml_documents_absorbed_module_path():
    """The shipped rule YAML must declare `absorbed_module:` pointing at
    the absorbed module so the audit trail from rule → implementation is
    discoverable per AC-UNIT-003."""
    import atdd

    repo_root = Path(atdd.__file__).resolve().parents[2]
    rule_path = (
        repo_root / ".atdd" / "observer" / "rules" / "06-token-threshold.yaml"
    )
    assert rule_path.exists(), (
        f"rule 06 must ship at {rule_path.relative_to(repo_root)}"
    )
    payload = yaml.safe_load(rule_path.read_text())
    absorbed = payload.get("absorbed_module")
    assert isinstance(absorbed, str) and absorbed, (
        "06-token-threshold.yaml MUST declare `absorbed_module:` pointing at "
        "the absorbed-functions module"
    )
    abs_path = repo_root / absorbed
    assert abs_path.exists(), (
        f"absorbed_module path {absorbed!r} must resolve to an existing file"
    )

    # The path must point at the token_threshold module (or sibling) that
    # actually defines the three absorbed functions.
    abs_text = abs_path.read_text()
    for fn in (
        "def load_token_alert_threshold",
        "def read_token_count",
        "def check_token_threshold",
    ):
        assert fn in abs_text, (
            f"absorbed_module {absorbed!r} missing definition: {fn}"
        )


def test_load_threshold_reads_coach_namespace_per_spec(tmp_path: Path):
    """The absorbed loader reads `coach.token_alert_threshold` per spec §10."""
    from atdd.coach.commands.token_threshold import load_token_alert_threshold

    cfg_dir = tmp_path / ".atdd"
    cfg_dir.mkdir()
    (cfg_dir / "config.yaml").write_text(
        "coach:\n  token_alert_threshold: 250000\n"
    )
    assert load_token_alert_threshold(repo_root=tmp_path) == 250_000
