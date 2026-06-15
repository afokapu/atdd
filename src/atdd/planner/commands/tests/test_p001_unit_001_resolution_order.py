# URN: test:author-atdd-substrate:substrate-spine:P001-UNIT-001-resolution-order
# Acceptance: acc:author-atdd-substrate:P001-UNIT-001-resolution-order
# WMBT: wmbt:author-atdd-substrate:P001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""P001-UNIT-001 — resolve_context follows the §6 resolution order."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_context import resolve_context


def test_core_flag_wins(tmp_path):
    ctx = resolve_context(core=True, extension="ignored", cwd=str(tmp_path))
    assert ctx.is_core and ctx.extension_id is None


def test_extension_flag(tmp_path):
    ctx = resolve_context(extension="bromohub.extension.alpha", cwd=str(tmp_path))
    assert not ctx.is_core and ctx.extension_id == "bromohub.extension.alpha"


def test_cwd_inside_extension(tmp_path):
    inside = tmp_path / "extensions" / "bromohub.extension.beta" / "conventions"
    inside.mkdir(parents=True)
    ctx = resolve_context(cwd=str(inside))
    assert ctx.extension_id == "bromohub.extension.beta"


def test_single_active_config(tmp_path):
    ctx = resolve_context(cwd=str(tmp_path), config_extensions=["bromohub.extension.gamma"])
    assert ctx.extension_id == "bromohub.extension.gamma"


def test_no_signal_fails(tmp_path):
    with pytest.raises(AuthorInputError) as exc:
        resolve_context(cwd=str(tmp_path))
    assert exc.value.field == "context"
