"""atdd author validates each built artifact against its canonical schema.

Regression guard for the gap where ``atdd author`` claimed "schema-valid by
construction" but only checked a hand-rolled required-field subset — silently
writing WMBTs the planner validators then rejected (non-kebab object_of_control,
out-of-vocabulary lens, bad enums). The writer now validates against
``planner/schemas/<kind>.schema.json`` (the same schema the validators enforce) and
fails fast naming every violation.
"""
from __future__ import annotations

import builtins
import logging

import pytest

from atdd.planner.commands.author import (
    AuthorInputError,
    create_wmbt,
    _load_schema,
)


def _wagon(root):
    d = root / "plan" / "demo-wagon"
    (d / "features").mkdir(parents=True)
    (d / "_demo-wagon.yaml").write_text("wagon: 'wagon:demo-wagon'\n")


def _spec(**over):
    base = dict(
        wagon_slug="demo-wagon",
        code="C011",
        step="confirm",
        direction="minimize",
        dimension="likelihood",
        lens="functional.effectiveness",
        object_of_control="a-kebab-object",
        statement="minimize likelihood of a-kebab-object by doing x",
    )
    base.update(over)
    return base


def test_accepts_schema_valid_wmbt(tmp_path):
    _wagon(tmp_path)
    assert create_wmbt(_spec(), root=tmp_path).name == "C011.yaml"


def test_rejects_non_kebab_object_of_control_via_schema(tmp_path):
    _wagon(tmp_path)
    with pytest.raises(AuthorInputError) as ei:
        create_wmbt(
            _spec(
                object_of_control="a-kebab-object spaced",
                statement="minimize likelihood of a-kebab-object spaced by x",
            ),
            root=tmp_path,
        )
    msg = str(ei.value)
    assert "wmbt.schema.json" in msg and "object_of_control" in msg


def test_rejects_out_of_vocabulary_lens_via_schema(tmp_path):
    _wagon(tmp_path)
    with pytest.raises(AuthorInputError) as ei:
        create_wmbt(_spec(lens="structural.modularity"), root=tmp_path)
    assert "lens" in str(ei.value)


def test_reports_all_violations_at_once(tmp_path):
    _wagon(tmp_path)
    with pytest.raises(AuthorInputError) as ei:
        create_wmbt(
            _spec(lens="structural.x", dimension="not-a-dimension"),
            root=tmp_path,
        )
    msg = str(ei.value)
    # both the lens and the dimension violations are named in one error
    assert "lens" in msg and "dimension" in msg and "violation(s)" in msg


def test_jsonschema_import_failure_is_observable(tmp_path, monkeypatch, caplog):
    _wagon(tmp_path)
    _load_schema.cache_clear()
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "jsonschema":
            raise ImportError("jsonschema missing")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    caplog.set_level(logging.WARNING, logger="atdd.planner.commands.author")

    assert create_wmbt(_spec(), root=tmp_path).name == "C011.yaml"
    assert "jsonschema unavailable" in caplog.text
