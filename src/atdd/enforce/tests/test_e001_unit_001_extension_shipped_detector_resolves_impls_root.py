# URN: test:govern-providers:E001-UNIT-001-extension-shipped-detector-resolves-impls-root
# Acceptance: acc:govern-providers:E001-UNIT-001-extension-shipped-detector-resolves-impls-root
# WMBT: wmbt:govern-providers:E001
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""GREEN Test for acc:govern-providers:E001-UNIT-001-extension-shipped-detector-resolves-impls-root.

A detector shipped ONLY under ``.atdd/extensions`` (nothing under ``.atdd/workspaces``)
is discovered and its own implementations root is resolved, exactly as a
workspace-shipped detector would be — the runner searches both vendored trees (#1359).
Before that fix an extension-shipped detector resolved to None and was reported
unrunnable while the aggregate verdict printed a false-green PASS.
"""
from __future__ import annotations

from pathlib import Path

from atdd.enforce.runner import _resolve_impls_root

from .conftest import build_enforce_substrate


def test_extension_shipped_detector_resolves_impls_root(tmp_path: Path) -> None:
    root = build_enforce_substrate(tmp_path, detector_in_extension=True)

    impls_root = _resolve_impls_root(root, "acme.rule.owned")

    assert impls_root is not None, "an extension-shipped detector must be discoverable"
    assert impls_root == (
        root / ".atdd" / "extensions" / "acme.extension.rules" / "0.1.0" / "implementations"
    )
