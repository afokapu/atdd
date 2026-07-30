# URN: test:govern-providers:E003-SMOKE-001-real-lock-has-no-extension-identity
# Acceptance: acc:govern-providers:E003-SMOKE-001-real-lock-has-no-extension-identity
# WMBT: wmbt:govern-providers:E003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:govern-providers:E003-SMOKE-001-real-lock-has-no-extension-identity.

The toolkit's own real committed ``.atdd/binding.lock.yaml`` carries no extension
PACKAGE identity string: ``atdd.extension.coder`` and ``atdd.extension.tester`` each
occur zero times, and every bound entry is keyed by convention_id + implementation_id.
So the persona rename stays a lock regeneration, not a rule migration.
"""
from __future__ import annotations

import yaml

from atdd.coach.utils.repo import find_repo_root


def test_real_lock_has_no_extension_identity() -> None:
    lock_path = find_repo_root() / ".atdd" / "binding.lock.yaml"
    text = lock_path.read_text(encoding="utf-8")

    assert text.count("atdd.extension.coder") == 0
    assert text.count("atdd.extension.tester") == 0

    lock = yaml.safe_load(text) or {}
    for entry in lock.get("conventions", []):
        assert "convention_id" in entry
        if entry.get("disposition") == "bound":
            assert "implementation_id" in entry
            # No entry is keyed by a package identity.
            assert not str(entry.get("implementation_id", "")).startswith("atdd.extension.")
