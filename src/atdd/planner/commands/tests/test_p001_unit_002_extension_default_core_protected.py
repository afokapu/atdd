# URN: test:author-atdd-substrate:substrate-spine:P001-UNIT-002-extension-default-core-protected
# Acceptance: acc:author-atdd-substrate:P001-UNIT-002-extension-default-core-protected
# WMBT: wmbt:author-atdd-substrate:P001
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""P001-UNIT-002 — extension is the default; core is never reached without --core."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError
from atdd.planner.commands.author_context import resolve_context

_EID = "bromohub.extension.alpha"


def test_default_is_never_core(tmp_path):
    assert not resolve_context(extension=_EID, cwd=str(tmp_path)).is_core
    # absent any signal, resolution fails — it never silently falls back to core
    with pytest.raises(AuthorInputError):
        resolve_context(cwd=str(tmp_path))


def test_core_requires_explicit_flag(tmp_path):
    assert resolve_context(core=True).is_core
    for kwargs in ({"extension": _EID}, {"config_extensions": [_EID]}):
        assert not resolve_context(cwd=str(tmp_path), **kwargs).is_core
