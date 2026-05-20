# URN: test:dispatch-ux-defaults-and-primer:coach-dispatch-env-aware-defaults:Y002-UNIT-001-banner-muted-when-marker-exists
# Acceptance: acc:dispatch-ux-defaults-and-primer:Y002-UNIT-001-banner-muted-when-marker-exists
# WMBT: wmbt:dispatch-ux-defaults-and-primer:Y002
# Phase: RED
# Layer: application
# Runtime: python
"""Y002-UNIT-001 — should_emit_upgrade_banner returns False when sync-acknowledged marker exists.

RED: should_emit_upgrade_banner does not exist in src/atdd/version_check.py.
The upgrade banner is printed on every atdd invocation even after the operator
has already run atdd sync, cluttering every subsequent command's output.
"""
from __future__ import annotations

import pytest

pytestmark = [pytest.mark.platform]

_CURRENT_VERSION = "3.77.0"


def test_banner_muted_when_marker_exists(tmp_path):
    """should_emit_upgrade_banner returns False when the sync-acknowledged marker exists."""
    from atdd import version_check

    fn = getattr(version_check, "should_emit_upgrade_banner", None)
    assert fn is not None, (
        "version_check.should_emit_upgrade_banner is not implemented — "
        "the banner cannot be suppressed after atdd sync (RED)"
    )

    # Create the marker file that atdd sync should write.
    marker_name = f"sync_acknowledged_{_CURRENT_VERSION}"
    (tmp_path / marker_name).touch()

    result = fn(current_version=_CURRENT_VERSION, marker_dir=tmp_path)
    assert result is False, (
        f"should_emit_upgrade_banner must return False when marker exists; got {result!r}"
    )


def test_banner_shown_when_no_marker(tmp_path):
    """should_emit_upgrade_banner returns True when no marker file exists."""
    from atdd import version_check

    fn = getattr(version_check, "should_emit_upgrade_banner", None)
    assert fn is not None, (
        "version_check.should_emit_upgrade_banner is not implemented (RED)"
    )

    result = fn(current_version=_CURRENT_VERSION, marker_dir=tmp_path)
    assert result is True, (
        f"should_emit_upgrade_banner must return True when no marker exists; got {result!r}"
    )


def test_banner_shown_when_marker_for_different_version(tmp_path):
    """should_emit_upgrade_banner returns True when marker is for an older version."""
    from atdd import version_check

    fn = getattr(version_check, "should_emit_upgrade_banner", None)
    assert fn is not None, (
        "version_check.should_emit_upgrade_banner is not implemented (RED)"
    )

    # Marker for old version — new upgrade happened.
    (tmp_path / "sync_acknowledged_3.76.0").touch()

    result = fn(current_version=_CURRENT_VERSION, marker_dir=tmp_path)
    assert result is True, (
        f"should_emit_upgrade_banner must return True for a new version "
        f"(marker is for old version); got {result!r}"
    )
