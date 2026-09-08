# URN: test:author-atdd-substrate:E009-UNIT-004-refused-write-exits-two-with-json-findings
# Acceptance: acc:author-atdd-substrate:E009-UNIT-004-refused-write-exits-two-with-json-findings
# WMBT: wmbt:author-atdd-substrate:E009
# Phase: RED
# Layer: unit
# Assertion: behavioral
"""RED Test for acc:author-atdd-substrate:E009-UNIT-004-refused-write-exits-two-with-json-findings.

The refusal has to be MACHINE-READABLE. The authoring agent's only correction loop is
"read the findings, fix the prose, re-run the same command" — core deliberately has no
LLM of its own. A bare traceback breaks that loop, so the dispatch boundary must render
one parseable JSON object and exit 2.
"""
from __future__ import annotations

import json

import pytest

from atdd.planner.commands import author

_FINDINGS = [{"rule_id": "planner.controlled-language.ste-conformance",
              "locations": ["wmbt.yaml:statement"], "detail": "Use an approved word."}]


def test_e009_unit_004_refused_write_exits_two_with_json_findings(capsys, monkeypatch):
    def _boom(args, ctx, root):
        raise author.ArtifactReviewError("wmbt", _FINDINGS)

    code = author._dispatch_review_errors(_boom, None, None, None)

    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["error"] == "artifact-review"
    assert payload["artifact_kind"] == "wmbt"
    assert payload["findings"] == _FINDINGS


def test_e009_unit_004_clean_run_is_passed_through_untouched(capsys):
    """The boundary must not swallow or reshape a normal result."""
    assert author._dispatch_review_errors(lambda a, c, r: 0, None, None, None) == 0
    assert capsys.readouterr().out == ""
