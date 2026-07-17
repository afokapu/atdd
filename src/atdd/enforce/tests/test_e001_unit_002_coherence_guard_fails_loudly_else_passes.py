# URN: test:govern-registry:E001-UNIT-002-coherence-guard-fails-loudly-else-passes
# Acceptance: acc:govern-registry:E001-UNIT-002-coherence-guard-fails-loudly-else-passes
# WMBT: wmbt:govern-registry:E001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-registry:E001-UNIT-002-coherence-guard-fails-loudly-else-passes.

When a mirror has drifted the guard raises loudly naming the drifted node; when
every mirror resolves to a live core rule it passes.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.enforce.registry import MirrorDriftError, assert_mirrors_coherent

from .conftest import write_mirror_node


def test_coherence_guard_fails_loudly_else_passes(tmp_path: Path) -> None:
    core_ids = {"coder.security.sql-injection"}

    # A drifted mirror → guard raises, naming the drifted node + missing rule.
    write_mirror_node(
        tmp_path,
        rule_id="coder.security.sql-injection-gone",
        legacy_rule_id="coder.security.sql-injection-gone",
    )
    with pytest.raises(MirrorDriftError) as exc:
        assert_mirrors_coherent(tmp_path, core_ids)
    message = str(exc.value)
    assert "coder.security.sql-injection-gone" in message

    # A coherent substrate → guard passes and returns an empty incoherence list.
    coherent = tmp_path / "coherent"
    write_mirror_node(
        coherent,
        rule_id="coder.security.sql-injection",
        legacy_rule_id="coder.security.sql-injection",
    )
    assert assert_mirrors_coherent(coherent, core_ids) == []
