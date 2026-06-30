# URN: component:govern-lifecycle:enforcement-substrate:test_fix_hint_completeness_helpers:backend:domain
# Runtime: python
# Purpose: Unit tests for the fix-hint completeness contract helpers (issue #467).

"""Helper-level coverage for the C1/C2/C3 audits and discovery utilities
implemented in ``test_fix_hint_completeness.py``.

The validator's main test exercises end-to-end behavior on the toolkit's
own tree; these helpers cover the pure-function building blocks with at
least one positive + one negative fixture per clause.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from atdd.coach.validators.test_fix_hint_completeness import (
    audit_c1_placeholder_resolution,
    audit_c2_no_deprecation_contradiction,
    build_deprecation_registry,
    load_negative_exemplars,
)


# ---------------------------------------------------------------------------
# C1 — placeholder resolution
# ---------------------------------------------------------------------------
class TestC1PlaceholderResolution:
    def test_no_placeholder_passes(self):
        assert audit_c1_placeholder_resolution(
            "Either fix the underlying violation or extend UNTIL= past today."
        ) == []

    def test_pipe_enumeration_resolves(self):
        # `<a|b|c>` carries its own value space.
        assert audit_c1_placeholder_resolution(
            "Add `disposition: <strict|suppress-and-clean|advisory>` to the rule."
        ) == []

    def test_function_call_context_resolves(self):
        # `bind_rule(<id>)` — placeholder inside parens of a call.
        assert audit_c1_placeholder_resolution(
            "Call bind_rule(<id>) at module-import time."
        ) == []

    def test_quoted_form_resolves(self):
        # `'<module>::<func>'` — placeholder inside single quotes.
        unresolved = audit_c1_placeholder_resolution(
            "Set validator: '<module>::<func>' on the rule."
        )
        assert unresolved == []

    def test_schema_descriptor_after_colon_resolves(self):
        # `key: <value>` — schema-descriptor pattern.
        assert audit_c1_placeholder_resolution(
            "signal.metric: <name> with signal.threshold: <value>"
        ) == []

    def test_path_template_continuation_resolves(self):
        # `<repo>/.atdd/...` — path-template continuation.
        assert audit_c1_placeholder_resolution(
            "Add the implementation in <repo>/.atdd/metrics/<name>.py"
        ) == []

    def test_explicit_resolver_line_resolves_anywhere(self):
        # Even a "loose" placeholder is resolved when an `e.g. "..."` line
        # is present in the same hint block.
        text = textwrap.dedent(
            """\
            Run the new validator with --train <train_id>.
            e.g. "0001-self-compliance-validate"
            """
        )
        assert audit_c1_placeholder_resolution(text) == []

    def test_bare_cli_arg_placeholder_fails(self):
        # Negative exemplar (issue #466 shape): `<train_id>` after a flag
        # with no resolver line.
        unresolved = audit_c1_placeholder_resolution(
            "atdd update <issue_id> --status <status> --train <train_id>"
        )
        assert "train_id" in unresolved
        assert "issue_id" in unresolved
        assert "status" in unresolved

    def test_multiple_unresolved_placeholders_all_reported(self):
        unresolved = audit_c1_placeholder_resolution(
            "atdd run <foo> --opt <bar>"
        )
        assert sorted(unresolved) == ["bar", "foo"]


# ---------------------------------------------------------------------------
# C2 — no deprecation contradiction
# ---------------------------------------------------------------------------
class TestC2DeprecationContradiction:
    REGISTRY = {
        "atdd update": "atdd issue <N> --status <S>",
        "atdd new": "atdd issue <slug>",
    }

    def test_canonical_form_passes(self):
        # `atdd issue` is the canonical replacement, not deprecated.
        assert (
            audit_c2_no_deprecation_contradiction(
                "atdd issue 467 --status RED", self.REGISTRY
            )
            is None
        )

    def test_unknown_command_passes(self):
        # `atdd validate` not in registry → not deprecated.
        assert (
            audit_c2_no_deprecation_contradiction(
                "Run: atdd validate coach", self.REGISTRY
            )
            is None
        )

    def test_no_atdd_command_passes(self):
        # Fix line that doesn't reference an `atdd` subcommand at all.
        assert (
            audit_c2_no_deprecation_contradiction(
                "git fetch origin main && git rebase origin/main",
                self.REGISTRY,
            )
            is None
        )

    def test_deprecated_form_fails(self):
        # Negative exemplar (#466 shape): `atdd update` is deprecated.
        result = audit_c2_no_deprecation_contradiction(
            "atdd update {issue_id} --status {status} --train <train_id>",
            self.REGISTRY,
        )
        assert result is not None
        head, canonical = result
        assert head == "atdd update"
        assert "atdd issue" in canonical

    # Flag-qualified deprecation (#1239): only `atdd list --substrate` is
    # deprecated; bare `atdd list` (issue listing, `atdd list trains`) is not.
    FLAG_REGISTRY = {"atdd list --substrate": "atdd substrate list"}

    def test_bare_subcommand_of_flag_qualified_deprecation_passes(self):
        # `atdd list trains` must NOT be flagged just because the
        # `--substrate` flag variant is deprecated.
        assert (
            audit_c2_no_deprecation_contradiction(
                "resolve via (run atdd list trains)", self.FLAG_REGISTRY
            )
            is None
        )

    def test_flag_qualified_form_fails_when_flag_present(self):
        result = audit_c2_no_deprecation_contradiction(
            "run: atdd list --substrate", self.FLAG_REGISTRY
        )
        assert result is not None
        form, canonical = result
        assert form == "atdd list --substrate"
        assert canonical == "atdd substrate list"


class TestDeprecationRegistryParse:
    def test_parses_callsites_from_source(self):
        source = textwrap.dedent(
            """
            def something():
                _deprecation_warning("atdd update <N> --status <S>", "atdd issue <N> --status <S>")
                _deprecation_warning("atdd archive <N>", "atdd issue <N> --status COMPLETE")
            """
        )
        registry = build_deprecation_registry(cli_source=source)
        assert registry.get("atdd update") == "atdd issue <N> --status <S>"
        assert registry.get("atdd archive") == "atdd issue <N> --status COMPLETE"

    def test_flag_qualified_deprecation_keeps_flag_in_key(self):
        # `atdd list --substrate` keys on the flagged form, not bare `atdd list`,
        # so the still-valid bare subcommand is never matched (#1239).
        source = textwrap.dedent(
            """
            def something():
                _deprecation_warning("atdd list --substrate", "atdd substrate list")
            """
        )
        registry = build_deprecation_registry(cli_source=source)
        assert registry.get("atdd list --substrate") == "atdd substrate list"
        assert "atdd list" not in registry

    def test_handles_empty_source(self):
        assert build_deprecation_registry(cli_source="") == {}


# ---------------------------------------------------------------------------
# Negative-exemplar parser
# ---------------------------------------------------------------------------
class TestNegativeExemplarLoader:
    def test_loads_owner_issue_and_line_range(self, tmp_path: Path):
        convention = tmp_path / "rule-id.convention.yaml"
        convention.write_text(
            textwrap.dedent(
                """\
                fix_hint_exemplars:
                  negative:
                    - source: "src/atdd/coach/commands/issue.py:1682-1684"
                      owner_issue: 466
                      why_fail: "bare placeholder + deprecated form"
                """
            )
        )
        out = load_negative_exemplars(convention)
        assert len(out) == 1
        path, start, end, owner = out[0]
        assert path == "src/atdd/coach/commands/issue.py"
        assert start == 1682
        assert end == 1684
        assert owner == 466

    def test_missing_block_returns_empty(self, tmp_path: Path):
        convention = tmp_path / "rule-id.convention.yaml"
        convention.write_text("schema_version: '1.0.0'\n")
        assert load_negative_exemplars(convention) == []
