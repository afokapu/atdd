# URN: urn:atdd:test:coach:commands:rules_cli
# Issue: #409

"""Unit tests for ``atdd rules`` and the ``atdd repo`` repo-rule listings.

Substrate spec v12 §9.2 — surface the merged rule registry to humans.

Coverage:

* ``atdd rules show <rule-id>`` (toolkit + repo, alias resolution, JSON,
  unknown-id error path).
* ``atdd rules where <rule-id>`` (source path + acceptance URN).
* ``atdd rules grep <pattern>`` (id-match, description-match, no-match).
* ``atdd repo rules`` (lists every repo rule, grouped by parent).
* ``atdd repo wmbt-rules <wmbt-urn>`` (single-WMBT filter).
* ``atdd repo train-rules <train-urn>`` (single-train filter).

The fixture builds a tmp-path consumer repo with two WMBT acceptances and
one train acceptance, then drives the registry through
``clear_cache(override_repo_root=...)`` so the tests are hermetic from the
toolkit's own ``plan/`` tree.
"""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent

import pytest


pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _reset_cache():
    from atdd.coach.utils.rule_binding import clear_cache

    clear_cache()
    yield
    clear_cache()


_WMBT_D010 = """
    urn: "wmbt:govern-lifecycle:D010"
    step: "define"
    direction: "minimize"
    dimension: "quantity"
    object_of_control: "duplicated-hardcoded-theme-map-dicts-across-modules"
    context_clarifier: "fixture mirroring D010.yaml"
    lens: "functional.sustainability"
    statement: "minimize duplicated hardcoded theme_map literals"
    acceptances:
      - identity:
          urn: "acc:govern-lifecycle:D010-UNIT-001-single-source-theme-map-helper"
          id: "AC-UNIT-001"
          purpose: "A single get_theme_map(config) helper replaces every hardcoded theme_map dict"
          phase: "GREEN"
        harness:
          type: "unit"
          category: "backend"
        given:
          abstract: ["coach/utils/theme_map.py exposes get_theme_map(config)"]
        when:
          abstract: "A grep for hardcoded theme_map dict literals runs across src/atdd"
        then:
          abstract:
            - "No theme_map dict literal appears outside coach/utils/theme_map.py"
        signal:
          metric: "hardcoded_theme_map_literal_count"
          threshold: 0
"""


_WMBT_D001 = """
    urn: "wmbt:foo-wagon:D001"
    step: "define"
    direction: "minimize"
    dimension: "quantity"
    object_of_control: "thing"
    context_clarifier: "ctx"
    lens: "functional.sustainability"
    statement: "stmt"
    acceptances:
      - identity:
          urn: "acc:foo-wagon:D001-HTTP-007-readability-slug"
          purpose: "HTTP harness acceptance for grammar coverage"
          phase: "RED"
        harness: { type: http }
"""


_TRAIN_FIXTURE = """
    train_id: "0001-self-compliance-validate"
    title: "Self-compliance validation train"
    description: "Fixture train carrying acceptances for the rules CLI test."
    themes: ["commons"]
    participants: ["wagon:govern-lifecycle"]
    sequence:
      - step: 1
        intent: "validate the toolkit against itself"
        from: "system:external"
        to: "wagon:govern-lifecycle"
        artifact: "atdd:self-validate"
    acceptances:
      - identity:
          urn: "acc:0001-self-compliance-validate:idempotent-on-retry"
          purpose: "Re-running the train with the same idempotency key is idempotent"
          phase: "SMOKE"
        harness:
          type: "e2e"
        signal:
          metric: "duplicate_side_effects_on_retry"
          threshold: 0
"""


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body).lstrip(), encoding="utf-8")
    return path


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """A tmp-path consumer repo seeded with WMBT + train acceptances.

    Layout:
      plan/govern_lifecycle/D010.yaml   (signal mode — `theme_map` rule)
      plan/foo_wagon/D001.yaml          (harness-only http acceptance)
      plan/_trains/0001-self-compliance-validate.yaml (train acceptance)
    """
    (tmp_path / "plan").mkdir()
    (tmp_path / "plan" / "_trains").mkdir()
    _write(tmp_path / "plan" / "govern_lifecycle" / "D010.yaml", _WMBT_D010)
    _write(tmp_path / "plan" / "foo_wagon" / "D001.yaml", _WMBT_D001)
    _write(
        tmp_path / "plan" / "_trains" / "0001-self-compliance-validate.yaml",
        _TRAIN_FIXTURE,
    )
    return tmp_path


@pytest.fixture
def seeded_registry(fixture_repo: Path):
    """Point the rule registry at the fixture repo and yield it for assertions.

    The override stays in effect for the duration of one test so every
    ``RulesCommand`` / ``RepoRulesListing`` call resolves against the
    fixture. Reset via the autouse ``_reset_cache``.
    """
    from atdd.coach.utils.rule_binding import clear_cache

    clear_cache(override_repo_root=fixture_repo)
    return fixture_repo


# ---------------------------------------------------------------------------
# atdd rules show
# ---------------------------------------------------------------------------
def test_rules_show_returns_repo_metadata_text(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``atdd rules show`` prints the bound RuleMetadata for a repo rule."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().show("repo.govern-lifecycle.D010-acc-unit-001")
    assert rc == 0
    out = capsys.readouterr().out
    assert "rule_id:" in out
    assert "repo.govern-lifecycle.D010-acc-unit-001" in out
    assert "severity:" in out
    assert "disposition:       strict" in out
    assert "acceptance_urn" in out
    assert "wmbt:govern-lifecycle:D010" in out


def test_rules_show_emits_json_when_requested(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``--format json`` produces a parseable RuleMetadata payload."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().show(
        "repo.govern-lifecycle.D010-acc-unit-001", format="json"
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["rule_id"] == "repo.govern-lifecycle.D010-acc-unit-001"
    assert payload["severity"] == 4
    assert payload["disposition"] == "strict"
    assert payload["wmbt_urn"] == "wmbt:govern-lifecycle:D010"
    assert payload["acceptance_urn"].startswith("acc:govern-lifecycle:D010-UNIT-001")
    # source_path serializes as string (not Path).
    assert isinstance(payload["source_path"], str)
    assert payload["source_path"].endswith("D010.yaml")


def test_rules_show_unknown_id_returns_nonzero_with_stderr(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """An unregistered rule-id surfaces as exit-1 with a message on stderr."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().show("does.not.exist")
    assert rc == 1
    captured = capsys.readouterr()
    assert "not declared in any convention" in captured.err
    # stdout stays clean — the message is for human eyes via stderr.
    assert captured.out == ""


# ---------------------------------------------------------------------------
# atdd rules where
# ---------------------------------------------------------------------------
def test_rules_where_prints_source_path_and_acceptance_urn(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``atdd rules where`` surfaces the YAML source + the derived acc URN."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().where("repo.govern-lifecycle.D010-acc-unit-001")
    assert rc == 0
    out = capsys.readouterr().out
    assert "source_path:" in out
    assert str(seeded_registry / "plan" / "govern_lifecycle" / "D010.yaml") in out
    assert "acceptance_urn:" in out
    assert "acc:govern-lifecycle:D010-UNIT-001-single-source-theme-map-helper" in out


def test_rules_where_json_keys_are_minimal(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """JSON output for ``where`` carries the three pointers — no kitchen sink."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().where(
        "repo.govern-lifecycle.D010-acc-unit-001", format="json"
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload.keys()) == {"rule_id", "source_path", "acceptance_urn"}
    assert payload["rule_id"] == "repo.govern-lifecycle.D010-acc-unit-001"
    assert payload["source_path"].endswith("D010.yaml")


# ---------------------------------------------------------------------------
# atdd rules grep
# ---------------------------------------------------------------------------
def test_rules_grep_matches_description_substring(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Grep filters by description text — the canonical acceptance criterion."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().grep("theme_map")
    assert rc == 0
    out = capsys.readouterr().out
    assert "repo.govern-lifecycle.D010-acc-unit-001" in out


def test_rules_grep_matches_rule_id(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Grep also matches against rule-id, not just description."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().grep(r"D010-acc-unit")
    assert rc == 0
    out = capsys.readouterr().out
    assert "repo.govern-lifecycle.D010-acc-unit-001" in out
    # Train rule id has no D010 in it — must NOT match.
    assert "repo.0001-self-compliance-validate.acc-idempotent-on-retry" not in out


def test_rules_grep_no_match_returns_nonzero(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """No match returns exit-1 (grep convention) with a friendly text line."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().grep("zzz_no_such_token_zzz")
    assert rc == 1
    out = capsys.readouterr().out
    assert "No rules matched" in out


def test_rules_grep_treats_regex_specials_as_literal_substring(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Issue #493 §AC-UNIT-003: grep is case-insensitive substring, not regex.

    Regex special characters (``(``, ``[``, ``*``...) are matched as literal
    text — the surface MUST NOT crash on a pattern like ``(unclosed`` and
    MUST NOT print a regex-compile error. With no such substring in the
    fixture registry the call returns the no-match exit-1 instead.
    """
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().grep("(unclosed")
    assert rc == 1
    captured = capsys.readouterr()
    assert "invalid regex" not in captured.err
    assert "No rules matched" in captured.out


# ---------------------------------------------------------------------------
# Issue #493 acc:L001-UNIT-001 — show resolves toolkit and repo + alias display
# ---------------------------------------------------------------------------
def test_rules_show_legacy_alias_displays_both_forms(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``atdd rules show <legacy-alias>`` prints input alias AND canonical id.

    Issue #493 acc:L001-UNIT-001 — when invoked with a legacy alias, the
    output must surface BOTH the legacy form (so the operator knows what
    they typed) and the canonical id (so they learn the canonical name).
    """
    from atdd.coach.commands.rules import RulesCommand

    # Real toolkit rule with a known legacy alias.
    rc = RulesCommand().show("COACH-ORCH-NAMING-0001")
    assert rc == 0
    out = capsys.readouterr().out
    # Both forms appear.
    assert "COACH-ORCH-NAMING-0001" in out
    assert "coach.orchestration.canonical-session-name" in out
    # Canonical metadata still printed.
    assert "severity:" in out
    assert "disposition:" in out


def test_rules_show_canonical_call_does_not_print_alias_resolution_header(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """When invoked with the canonical id, no legacy-alias resolution noise."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().show("coach.orchestration.canonical-session-name")
    assert rc == 0
    out = capsys.readouterr().out
    # The canonical line is present.
    assert "coach.orchestration.canonical-session-name" in out
    # The alias-resolution header line MUST NOT appear when input is canonical.
    assert "legacy alias" not in out.lower()


# ---------------------------------------------------------------------------
# Issue #493 acc:L001-UNIT-002 — where prints validator <module>::<function>
# ---------------------------------------------------------------------------
def test_rules_where_prints_module_function_for_toolkit_rule(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Issue #493 acc:L001-UNIT-002 — toolkit rule emits validator + path.

    For a toolkit-archetype rule with a declared ``validator:`` field,
    ``where`` must print the ``<module>::<function>`` reference and the
    inferred archetype-relative path
    (``src/atdd/<archetype>/validators/<module>.py``).
    """
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().where("coach.orchestration.canonical-session-name")
    assert rc == 0
    out = capsys.readouterr().out
    # validator field surfaced.
    assert "test_orchestration_session_naming::test_active_session_names_canonical" in out
    # Inferred import path includes the archetype dir.
    assert "coach/validators/test_orchestration_session_naming.py" in out


def test_rules_where_prints_substrate_dispatcher_for_repo_signal_rule(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Repo signal-mode rules carry the substrate metric runner as validator."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().where("repo.govern-lifecycle.D010-acc-unit-001")
    assert rc == 0
    out = capsys.readouterr().out
    # The walker pins signal-mode acceptances to the toolkit metric runner.
    assert "test_metric_runner::test_metric_threshold_satisfied" in out
    # The repo-rule source path (the WMBT YAML) is still surfaced.
    assert "D010.yaml" in out


def test_rules_where_resolves_legacy_alias_to_canonical_validator(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``where`` accepts a legacy alias and resolves to the canonical binding."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().where("COACH-ORCH-NAMING-0001")
    assert rc == 0
    out = capsys.readouterr().out
    assert "test_orchestration_session_naming::test_active_session_names_canonical" in out


def test_rules_where_unknown_rule_id_returns_nonzero(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Unregistered rule-id exits 1 with a clear stderr message (no stack trace)."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().where("does.not.exist")
    assert rc == 1
    captured = capsys.readouterr()
    assert "not declared in any convention" in captured.err
    assert captured.out == ""


# ---------------------------------------------------------------------------
# Issue #493 acc:L001-UNIT-003 — grep substring + alias + uniform output
# ---------------------------------------------------------------------------
def test_rules_grep_is_case_insensitive_substring(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Issue #493 acc:L001-UNIT-003 — grep matches the literal substring (case-insensitive)."""
    from atdd.coach.commands.rules import RulesCommand

    # Uppercase pattern matches a description authored in lowercase.
    rc = RulesCommand().grep("THEME_MAP")
    assert rc == 0
    out = capsys.readouterr().out
    assert "repo.govern-lifecycle.D010-acc-unit-001" in out


def test_rules_grep_searches_aliases(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Grep matches against legacy aliases — surface the canonical rule.

    Issue #493 acc:L001-UNIT-003 — the search domain explicitly includes
    aliases so an operator who only knows the legacy id can still find
    the canonical rule via grep.
    """
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().grep("COACH-ORCH-NAMING-0001")
    assert rc == 0
    out = capsys.readouterr().out
    # The canonical rule is surfaced even though the pattern is the alias.
    assert "coach.orchestration.canonical-session-name" in out


def test_rules_grep_each_line_shows_severity_disposition_description(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Issue #493 acc:L001-UNIT-003 — grep lines carry id+severity+disposition+description."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().grep("theme_map")
    assert rc == 0
    out = capsys.readouterr().out
    # The match line carries severity (sev=) and disposition (strict).
    # Walker constants: severity=4, disposition='strict'.
    assert "sev=4" in out
    assert "strict" in out
    # The description (purpose) text is on the same surface.
    assert "theme_map" in out


# ---------------------------------------------------------------------------
# atdd repo rules — list every repo rule, grouped by parent URN
# ---------------------------------------------------------------------------
def test_urn_rules_lists_every_repo_rule_grouped_by_parent(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``atdd repo rules`` shows every repo-derived rule across WMBT + train."""
    from atdd.coach.commands.rules import RepoRulesListing

    rc = RepoRulesListing().list_all_repo_rules()
    assert rc == 0
    out = capsys.readouterr().out
    # Every fixture rule appears.
    assert "repo.govern-lifecycle.D010-acc-unit-001" in out
    assert "repo.foo-wagon.D001-acc-http-007" in out
    assert "repo.0001-self-compliance-validate.acc-idempotent-on-retry" in out
    # Grouped by parent URN.
    assert "wmbt:govern-lifecycle:D010" in out
    assert "wmbt:foo-wagon:D001" in out
    assert "train:0001-self-compliance-validate" in out


def test_urn_rules_json_serializes_list(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """JSON output is a flat list of RuleMetadata dicts."""
    from atdd.coach.commands.rules import RepoRulesListing

    rc = RepoRulesListing().list_all_repo_rules(format="json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 3
    rule_ids = {entry["rule_id"] for entry in payload}
    assert rule_ids == {
        "repo.govern-lifecycle.D010-acc-unit-001",
        "repo.foo-wagon.D001-acc-http-007",
        "repo.0001-self-compliance-validate.acc-idempotent-on-retry",
    }


# ---------------------------------------------------------------------------
# atdd repo wmbt-rules <wmbt-urn>
# ---------------------------------------------------------------------------
def test_urn_wmbt_rules_filters_to_one_wmbt(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Filtering by WMBT URN returns only that WMBT's derived rules."""
    from atdd.coach.commands.rules import RepoRulesListing

    rc = RepoRulesListing().list_rules_for_wmbt("wmbt:govern-lifecycle:D010")
    assert rc == 0
    out = capsys.readouterr().out
    assert "repo.govern-lifecycle.D010-acc-unit-001" in out
    # Other parents must not leak in.
    assert "repo.foo-wagon.D001-acc-http-007" not in out
    assert "repo.0001-self-compliance-validate.acc-idempotent-on-retry" not in out


def test_urn_wmbt_rules_unknown_wmbt_returns_nonzero(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """An unrecognized WMBT URN reports zero matches with exit-1."""
    from atdd.coach.commands.rules import RepoRulesListing

    rc = RepoRulesListing().list_rules_for_wmbt("wmbt:nobody:Z999")
    assert rc == 1
    out = capsys.readouterr().out
    assert "No repo rules derived from wmbt:nobody:Z999" in out


def test_urn_wmbt_rules_rejects_non_wmbt_urn(
    capsys: pytest.CaptureFixture[str],
):
    """A URN that isn't ``wmbt:...`` is rejected before the registry walk."""
    from atdd.coach.commands.rules import RepoRulesListing

    rc = RepoRulesListing().list_rules_for_wmbt("train:foo")
    assert rc == 1
    err = capsys.readouterr().err
    assert "expected WMBT URN" in err


# ---------------------------------------------------------------------------
# atdd repo train-rules <train-urn>
# ---------------------------------------------------------------------------
def test_urn_train_rules_filters_to_one_train(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Filtering by train URN returns only that train's derived rules."""
    from atdd.coach.commands.rules import RepoRulesListing

    rc = RepoRulesListing().list_rules_for_train(
        "train:0001-self-compliance-validate"
    )
    assert rc == 0
    out = capsys.readouterr().out
    assert "repo.0001-self-compliance-validate.acc-idempotent-on-retry" in out
    # WMBT-derived rules don't leak into a train query.
    assert "repo.govern-lifecycle.D010-acc-unit-001" not in out


def test_urn_train_rules_rejects_non_train_urn(
    capsys: pytest.CaptureFixture[str],
):
    """A URN that isn't ``train:...`` is rejected before the registry walk."""
    from atdd.coach.commands.rules import RepoRulesListing

    rc = RepoRulesListing().list_rules_for_train("wmbt:foo:D001")
    assert rc == 1
    err = capsys.readouterr().err
    assert "expected train URN" in err


# ---------------------------------------------------------------------------
# iter_rules public API smoke test (exposed for #409 §9.2)
# ---------------------------------------------------------------------------
def test_iter_rules_emits_each_canonical_rule_once(seeded_registry: Path):
    """``iter_rules`` is the public peer of ``_get_registry`` — yields canonicals."""
    from atdd.coach.utils.rule_binding import iter_rules

    rules = list(iter_rules())
    rule_ids = [m.rule_id for m in rules]
    # Repo rules from the fixture appear exactly once.
    repo_ids = [rid for rid in rule_ids if rid.startswith("repo.")]
    assert len(repo_ids) == 3
    assert set(repo_ids) == {
        "repo.govern-lifecycle.D010-acc-unit-001",
        "repo.foo-wagon.D001-acc-http-007",
        "repo.0001-self-compliance-validate.acc-idempotent-on-retry",
    }
    # No duplicates anywhere.
    assert len(set(rule_ids)) == len(rule_ids)
