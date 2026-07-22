# URN: test:govern-registry:E002-SMOKE-001-real-merge-would-duplicate-every-mirror
# Acceptance: acc:govern-registry:E002-SMOKE-001-real-merge-would-duplicate-every-mirror
# WMBT: wmbt:govern-registry:E002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""SMOKE Test for acc:govern-registry:E002-SMOKE-001-real-merge-would-duplicate-every-mirror.

Over the real substrate, merging the extension mirror set into the core registry
would collide on every extension rule_id and raise DuplicateRuleError — the
concrete evidence behind the core-only decision.
"""
from __future__ import annotations

import pytest

from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import DuplicateRuleError
from atdd.enforce.registry import (
    assert_core_precedes_extension,
    core_rule_ids,
    duplicate_rule_ids,
    extension_rule_ids,
)


def test_real_merge_would_duplicate_every_mirror() -> None:
    repo = find_repo_root()
    core = core_rule_ids()
    ext = extension_rule_ids(repo)
    assert ext, "no extension convention nodes found under .atdd/extensions"

    # A merge is not silently tolerated: it raises over the real registries.
    with pytest.raises(DuplicateRuleError):
        assert_core_precedes_extension(core, ext)

    # The collisions are EXACTLY the full extension set — admitting the mirrors
    # would add only duplicates, never a new rule.
    assert duplicate_rule_ids(core, ext) == ext
