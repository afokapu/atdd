# URN: test:author-atdd-substrate:substrate-spine:C001-UNIT-002-spine-rejects-bad-id-and-path
# Acceptance: acc:author-atdd-substrate:C001-UNIT-002-spine-rejects-bad-id-and-path
# WMBT: wmbt:author-atdd-substrate:C001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""C001-UNIT-002 — the spine rejects a malformed id and a path outside the home.

Two independent rejections: a syntactically invalid / non-role-prefixed
rule_id, and a path that escapes the kind's canonical home (e.g. `..`
traversal). Both must fail before any writer runs.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.planner.commands.author import AuthorInputError, validate_author_input


def test_spine_rejects_malformed_rule_id():
    # role-prefixed but contains an illegal uppercase / underscore segment
    with pytest.raises(AuthorInputError) as exc:
        validate_author_input(
            role="coder",
            rule_id="coder.Green.BAD_ID",
            path=Path("src/atdd/coder/conventions/nodes/x.convention.yaml"),
        )
    assert exc.value.field == "rule_id"


def test_spine_rejects_non_role_prefixed_rule_id():
    with pytest.raises(AuthorInputError) as exc:
        validate_author_input(
            role="coder",
            rule_id="tester.green.component-urn-marker-is",  # prefix != role
            path=Path("src/atdd/coder/conventions/nodes/x.convention.yaml"),
        )
    assert exc.value.field == "rule_id"


def test_spine_rejects_path_escaping_home():
    with pytest.raises(AuthorInputError) as exc:
        validate_author_input(
            role="coder",
            rule_id="coder.green.component-urn-marker-is",
            path=Path("src/atdd/coder/conventions/nodes/../../../../etc/passwd"),
        )
    assert exc.value.field == "path"
