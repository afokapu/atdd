# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:Y002-UNIT-002-atdd-sync-writes-marker
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y002-UNIT-002-atdd-sync-writes-marker
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y002
# Phase: RED
# Layer: application
# Runtime: python
"""Y002-UNIT-002 — running atdd sync writes the sync-acknowledged marker file.

RED: The atdd sync command does not write a sync-acknowledged marker file.
Without the marker, should_emit_upgrade_banner always returns True and the
upgrade banner is shown on every invocation after sync.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]

_CURRENT_VERSION = "3.77.0"


def test_sync_writes_sync_acknowledged_marker(tmp_path, monkeypatch):
    """atdd sync writes sync_acknowledged_{version} marker in the runtime marker dir."""
    from atdd.coach.commands import sync as sync_module

    write_fn = getattr(sync_module, "write_sync_acknowledged_marker", None)
    assert write_fn is not None, (
        "sync.write_sync_acknowledged_marker is not implemented — "
        "atdd sync cannot write the sync-acknowledged marker (RED)"
    )

    write_fn(current_version=_CURRENT_VERSION, marker_dir=tmp_path)

    expected_marker = tmp_path / f"sync_acknowledged_{_CURRENT_VERSION}"
    assert expected_marker.exists(), (
        f"write_sync_acknowledged_marker must create {expected_marker.name} "
        f"in {tmp_path}; files present: {list(tmp_path.iterdir())}"
    )


def test_subsequent_banner_check_returns_false_after_sync(tmp_path):
    """After write_sync_acknowledged_marker, should_emit_upgrade_banner returns False."""
    from atdd.coach.commands import sync as sync_module
    from atdd import version_check

    write_fn = getattr(sync_module, "write_sync_acknowledged_marker", None)
    assert write_fn is not None, (
        "sync.write_sync_acknowledged_marker is not implemented (RED)"
    )

    banner_fn = getattr(version_check, "should_emit_upgrade_banner", None)
    assert banner_fn is not None, (
        "version_check.should_emit_upgrade_banner is not implemented (RED)"
    )

    write_fn(current_version=_CURRENT_VERSION, marker_dir=tmp_path)
    result = banner_fn(current_version=_CURRENT_VERSION, marker_dir=tmp_path)

    assert result is False, (
        f"should_emit_upgrade_banner must return False after sync writes marker; "
        f"got {result!r}"
    )
