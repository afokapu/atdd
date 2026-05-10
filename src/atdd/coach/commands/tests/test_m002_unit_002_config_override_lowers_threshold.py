# URN: test:observe-and-correct:observer-runtime-and-rules:M002-UNIT-002-config-override-lowers-threshold
# Acceptance: acc:observe-and-correct:M002-UNIT-002-config-override-lowers-threshold
# WMBT: wmbt:observe-and-correct:M002
# Phase: GREEN
# Layer: application
"""M002-UNIT-002 — Setting `coach.token_alert_threshold: 350000` in
`.atdd/config.yaml` lowers the firing threshold accordingly: a reading
at 360k tokens fires rule 06; a reading at 340k under the same config
does NOT fire.

Issue #507 (L3). Spec: `atdd-coach-spec-v9.md` §10 (config key).
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = [pytest.mark.platform]


def _write_config(repo_root: Path, threshold: int) -> Path:
    cfg_dir = repo_root / ".atdd"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / "config.yaml"
    cfg.write_text(f"coach:\n  token_alert_threshold: {threshold}\n")
    return cfg


def test_load_threshold_reads_coach_token_alert_threshold(tmp_path: Path):
    """`load_token_alert_threshold` must honor `coach.token_alert_threshold`
    per spec §10."""
    from atdd.coach.commands.token_threshold import load_token_alert_threshold

    _write_config(tmp_path, 350_000)
    assert load_token_alert_threshold(repo_root=tmp_path) == 350_000


def test_load_threshold_falls_back_to_default_when_unset(tmp_path: Path):
    """Without config, the default 400k threshold is used."""
    from atdd.coach.commands.token_threshold import (
        DEFAULT_TOKEN_ALERT_THRESHOLD,
        load_token_alert_threshold,
    )

    assert (
        load_token_alert_threshold(repo_root=tmp_path)
        == DEFAULT_TOKEN_ALERT_THRESHOLD
        == 400_000
    )


def test_360k_fires_when_config_lowers_threshold_to_350k(tmp_path: Path):
    """With threshold 350k, a 360k reading fires rule 06."""
    from atdd.coach.commands import observer
    from atdd.coach.commands.token_threshold import load_token_alert_threshold

    _write_config(tmp_path, 350_000)

    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "06-token-threshold.yaml").write_text(
        """\
rule_id: "06-token-threshold"
correction_text: "Approaching context limit. Run /compact."
trigger:
  type: token_threshold
injection_method: cli-return
severity: 3
disposition: advisory
absorbed_module: "src/atdd/coach/commands/token_threshold.py"
"""
    )

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)

    threshold = load_token_alert_threshold(repo_root=tmp_path)
    assert threshold == 350_000

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
    )
    obs.load_rules()

    with patch(
        "atdd.coach.commands.token_threshold.read_token_count",
        return_value=360_000,
    ):
        with patch(
            "atdd.coach.commands.token_threshold.load_token_alert_threshold",
            return_value=threshold,
        ):
            corrections = obs.scan_once()

    assert len(corrections) == 1, "360k must fire when threshold lowered to 350k"


def test_340k_does_not_fire_when_config_lowers_threshold_to_350k(tmp_path: Path):
    """With threshold 350k, a 340k reading does NOT fire rule 06."""
    from atdd.coach.commands import observer
    from atdd.coach.commands.token_threshold import load_token_alert_threshold

    _write_config(tmp_path, 350_000)

    rules_dir = tmp_path / ".atdd" / "observer" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / "06-token-threshold.yaml").write_text(
        """\
rule_id: "06-token-threshold"
correction_text: "Approaching context limit. Run /compact."
trigger:
  type: token_threshold
injection_method: cli-return
severity: 3
disposition: advisory
absorbed_module: "src/atdd/coach/commands/token_threshold.py"
"""
    )

    runtime = tmp_path / ".atdd" / "runtime"
    agent_dir = runtime / "agents" / "agent-A"
    agent_dir.mkdir(parents=True)

    threshold = load_token_alert_threshold(repo_root=tmp_path)
    assert threshold == 350_000

    obs = observer.Observer(
        agent_id="agent-A",
        runtime_dir=runtime,
        rules_dir=rules_dir,
    )
    obs.load_rules()

    with patch(
        "atdd.coach.commands.token_threshold.read_token_count",
        return_value=340_000,
    ):
        with patch(
            "atdd.coach.commands.token_threshold.load_token_alert_threshold",
            return_value=threshold,
        ):
            corrections = obs.scan_once()

    assert corrections == [], (
        "340k must not fire when threshold is 350k"
    )
