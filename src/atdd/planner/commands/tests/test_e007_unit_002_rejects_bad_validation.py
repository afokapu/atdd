# URN: test:author-atdd-substrate:author-convention-node:E007-UNIT-002-rejects-bad-validation-before-write
# Acceptance: acc:author-atdd-substrate:E007-UNIT-002-rejects-bad-validation-before-write
# WMBT: wmbt:author-atdd-substrate:E007
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""E007-UNIT-002 — an unknown family, an unregistered (family, template) pair, and
embedded concrete runtime state are rejected before any node file is written."""
from __future__ import annotations

import pytest

from atdd.planner.commands.author import AuthorInputError, create_convention_node

_TERMS = [{"term_id": "interlocking", "text": "the route-control model for the train domain"}]
_RID = "planner.train.interlocking-bad"


def _create(validation: dict, tmp_path):
    return create_convention_node(
        "planner", _RID,
        statement="x", terms=_TERMS, validation=validation, root=tmp_path,
    )


def _node_dir(tmp_path):
    return tmp_path / "src" / "atdd" / "planner" / "conventions" / "nodes"


def test_rejects_unknown_family(tmp_path):
    with pytest.raises(AuthorInputError) as exc:
        _create({"family": "not-a-real-family"}, tmp_path)
    assert exc.value.field == "family"
    assert not (_node_dir(tmp_path)).exists() or not list(_node_dir(tmp_path).glob("*.yaml"))


def test_rejects_unregistered_family_template_pair(tmp_path):
    with pytest.raises(AuthorInputError) as exc:
        _create({"family": "coherence", "template": "required_field_presence"}, tmp_path)
    assert exc.value.field == "template"
    assert not (_node_dir(tmp_path)).exists() or not list(_node_dir(tmp_path).glob("*.yaml"))


@pytest.mark.parametrize(
    "validation, field",
    [
        ({"family": "coherence", "config": {"train_id": "0007-demo"}}, "validation"),
        ({"family": "coherence", "route_selection": {"chosen": "main"}}, "validation"),
        ({"family": "coherence", "config": {"cargo": {"payload": 1}}}, "validation"),
        ({"family": "coherence", "config": {"rendered_digest": "deadbeef"}}, "validation"),
        ({"family": "coherence", "config": {"train_result": "PASS"}}, "validation"),
    ],
)
def test_rejects_concrete_runtime_state(validation, field, tmp_path):
    with pytest.raises(AuthorInputError) as exc:
        _create(validation, tmp_path)
    assert exc.value.field == field
    assert not (_node_dir(tmp_path)).exists() or not list(_node_dir(tmp_path).glob("*.yaml"))
