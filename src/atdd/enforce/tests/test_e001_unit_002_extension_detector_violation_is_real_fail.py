# URN: test:govern-providers:E001-UNIT-002-extension-detector-violation-is-real-fail-not-false-green
# Acceptance: acc:govern-providers:E001-UNIT-002-extension-detector-violation-is-real-fail-not-false-green
# WMBT: wmbt:govern-providers:E001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-providers:E001-UNIT-002-extension-detector-violation-is-real-fail-not-false-green.

Driving the real ``enforce`` runner over a substrate whose only bound detector is
extension-shipped turns an injected violation into a FAIL verdict and exit 1 —
never a silently-passing false green. A workspace-shipped detector still resolves,
proving forwarding ``--impls-root`` did not regress the workspace path.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.runner import enforce

from .conftest import build_enforce_substrate


def test_extension_detector_violation_is_a_real_fail(tmp_path: Path) -> None:
    root = build_enforce_substrate(tmp_path, detector_in_extension=True)

    result = enforce(root, path_override=["consumer"])

    statuses = {v.rule_id: v.status for v in result.verdicts}
    assert statuses == {"acme.rule.owned": "fail"}, "the injected violation must surface as FAIL"
    assert result.exit_code == 1
    assert not result.passed


def test_workspace_shipped_detector_still_resolves(tmp_path: Path) -> None:
    root = build_enforce_substrate(tmp_path, detector_in_extension=False)

    result = enforce(root, path_override=["consumer"])

    assert [v.status for v in result.verdicts] == ["fail"]


def test_absent_implementation_is_unrunnable_not_silently_passing(tmp_path: Path) -> None:
    """The honest counterpart to a false green: a bound convention whose impl is not
    discoverable is reported ``unrunnable``, never silently ``pass``."""
    root = build_enforce_substrate(tmp_path, detector_in_extension=True)
    (root / ".atdd" / "binding.lock.yaml").write_text(
        "schema_version: 1.0.0\nconventions:\n"
        "- convention_id: acme.rule.owned\n  disposition: bound\n"
        "  implementation_id: acme.rule.ghost\n"
        "  workspace_id: atdd.workspace.python-pytest\n  contract_version: 1.1.0\n",
        encoding="utf-8",
    )

    result = enforce(root, path_override=["consumer"])

    assert [v.status for v in result.verdicts] == ["unrunnable"]
