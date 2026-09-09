# URN: test:govern-lifecycle:govern-lifecycle:R011-UNIT-001-both-entry-points-return-rather-than-raise
# Acceptance: acc:govern-lifecycle:R011-UNIT-001-both-entry-points-return-rather-than-raise
# WMBT: wmbt:govern-lifecycle:R011
# Phase: RED
# Layer: application
"""R011-UNIT-001 — the two surfaces that read the deleted local must answer.

Deliberately asserts the ABSENCE of a `files` key as well as the presence of an
answer. The projection that produced it was retired on purpose (#1811/#1812);
making these surfaces work by resurrecting `_get_synced_files` would undo a
decision this repository already made, so the acceptance forbids it.
"""
from __future__ import annotations

import json as json_module

import pytest

from atdd.coach.commands.gate import ATDDGate


@pytest.mark.coder
def test_the_json_form_returns_parseable_json_instead_of_raising(tmp_path, capsys):
    rc = ATDDGate(target_dir=tmp_path).verify(json=True)

    assert rc == 0, "the JSON form must report, not fail"
    payload = json_module.loads(capsys.readouterr().out)
    assert "constraints" in payload, "the diagnostic payload must survive"
    assert "files" not in payload, (
        "the agent-config projection was retired in #1811/#1812; re-introducing a "
        "`files` key would revive what that change deliberately removed"
    )


@pytest.mark.coder
def test_the_confirmation_template_returns_a_string_instead_of_raising(tmp_path):
    template = ATDDGate(target_dir=tmp_path).get_confirmation_template()

    assert isinstance(template, str) and template.strip(), "the template must render"
    assert "ATDD Gate Confirmation" in template
    assert "hash:" not in template, (
        "the per-agent file listing came from the retired projection and must not "
        "come back"
    )


@pytest.mark.coder
def test_the_human_readable_form_is_untouched(tmp_path, capsys):
    """The path agents actually run at bootstrap keeps working."""
    rc = ATDDGate(target_dir=tmp_path).verify()

    assert rc == 0
    assert "ATDD Gate Verification" in capsys.readouterr().out
