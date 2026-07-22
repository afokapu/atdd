# URN: test:govern-registry:D001-SMOKE-001-real-registry-roots-at-core-only
# Acceptance: acc:govern-registry:D001-SMOKE-001-real-registry-roots-at-core-only
# WMBT: wmbt:govern-registry:D001
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:govern-registry:D001-SMOKE-001-real-registry-roots-at-core-only.

Over the toolkit's real substrate the core rule registry admits zero extension
files and every real extension rule_id already exists in the core registry, so the
core-only scope holds live.
"""
from __future__ import annotations

from atdd.coach.utils.repo import find_repo_root
from atdd.enforce.registry import (
    core_convention_files,
    core_rule_ids,
    extension_rule_ids,
    new_rules_from_extensions,
)


def test_real_registry_roots_at_core_only() -> None:
    repo = find_repo_root()

    # No file admitted into the core registry lives under .atdd/extensions.
    admitted = core_convention_files()
    assert admitted, "core registry unexpectedly empty"
    assert not any(".atdd/extensions" in str(p) for p in admitted)

    core = core_rule_ids()
    ext = extension_rule_ids(repo)
    assert ext, "no extension convention nodes found under .atdd/extensions"

    # Every extension rule_id is already a core rule_id — the extension-only set
    # is empty, so admitting the extensions would add no new rule.
    assert new_rules_from_extensions(core, ext) == set()
    assert ext <= core
