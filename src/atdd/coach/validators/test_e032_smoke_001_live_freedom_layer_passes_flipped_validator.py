# URN: test:spawn-agents:scoped-bash-freedom-set-config-driven:E032-SMOKE-001-live-freedom-layer-passes-flipped-validator
# Acceptance: acc:spawn-agents:E032-SMOKE-001-live-freedom-layer-passes-flipped-validator
# WMBT: wmbt:spawn-agents:E032
# Phase: SMOKE
# Layer: smoke
# Assertion: behavioral
"""E032-SMOKE-001 — the deployed session.convention.yaml::spawn_time.freedom_layer
passes the flipped freedom-set validator with zero violations: no forbidden command
in allowed_bash, every Bash entry tightly scoped.

SMOKE: loads the installed convention + the real validator (no synthetic fixture).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

_SCOPED_RE = re.compile(r"^Bash\([^()]+:\*\)$")


def _live_freedom_layer() -> dict:
    import atdd.coach.commands.spawn as spawn

    convention = (
        Path(spawn.__file__).resolve().parent.parent
        / "conventions"
        / "session.convention.yaml"
    )
    return yaml.safe_load(convention.read_text(encoding="utf-8"))["spawn_time"][
        "freedom_layer"
    ]


@pytest.mark.smoke
def test_live_freedom_layer_passes_flipped_validator():
    from atdd.coach.validators.freedom_layer_validator import (
        check_freedom_layer_allowlist_safety,
    )

    violations = check_freedom_layer_allowlist_safety(_live_freedom_layer())
    assert violations == [], (
        "E032-SMOKE-001: deployed freedom_layer has flipped-validator violations:\n"
        + "\n".join(f"  - {v}" for v in violations)
    )


@pytest.mark.smoke
def test_every_live_allowed_bash_entry_is_scoped():
    allowed_bash = _live_freedom_layer().get("allowed_bash") or []
    assert allowed_bash, "E032-SMOKE-001: live freedom_layer declares no allowed_bash"
    for entry in allowed_bash:
        assert _SCOPED_RE.match(entry), (
            f"E032-SMOKE-001: live allowed_bash entry {entry!r} is not tightly scoped "
            "Bash(<cmd>:*)"
        )
