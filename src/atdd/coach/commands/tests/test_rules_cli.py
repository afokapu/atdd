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


def test_rules_where_json_carries_validator_callsites_and_pointers(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """JSON output for ``where`` carries validator callsites and source pointers.

    Issue #493 acc:L001-UNIT-002 — the ``--format json`` payload exposes
    the validator ``<module>::<function>`` reference, the inferred
    module path, and (for repo rules) the source YAML + acceptance URN.
    """
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().where(
        "repo.govern-lifecycle.D010-acc-unit-001", format="json"
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload.keys()) == {
        "rule_id",
        "validator",
        "callsites",
        "source_path",
        "acceptance_urn",
    }
    assert payload["rule_id"] == "repo.govern-lifecycle.D010-acc-unit-001"
    assert payload["source_path"].endswith("D010.yaml")
    # Walker pinned signal-mode acceptances at the metric runner.
    assert payload["validator"] == (
        "test_metric_runner::test_metric_threshold_satisfied"
    )
    assert isinstance(payload["callsites"], list)
    assert len(payload["callsites"]) == 1
    assert (
        payload["callsites"][0]["validator_field"]
        == "test_metric_runner::test_metric_threshold_satisfied"
    )


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
    rc = RulesCommand().show("COACH-SESSION-NAMING-0001")
    assert rc == 0
    out = capsys.readouterr().out
    # Both forms appear.
    assert "COACH-SESSION-NAMING-0001" in out
    assert "coach.session.canonical-session-name" in out
    # Canonical metadata still printed.
    assert "severity:" in out
    assert "disposition:" in out


def test_rules_show_canonical_call_does_not_print_alias_resolution_header(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """When invoked with the canonical id, no legacy-alias resolution noise."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().show("coach.session.canonical-session-name")
    assert rc == 0
    out = capsys.readouterr().out
    # The canonical line is present.
    assert "coach.session.canonical-session-name" in out
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

    rc = RulesCommand().where("coach.session.canonical-session-name")
    assert rc == 0
    out = capsys.readouterr().out
    # validator field surfaced.
    assert "test_session_naming::test_active_session_names_canonical" in out
    # Inferred import path includes the archetype dir.
    assert "coach/validators/test_session_naming.py" in out


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

    rc = RulesCommand().where("COACH-SESSION-NAMING-0001")
    assert rc == 0
    out = capsys.readouterr().out
    assert "test_session_naming::test_active_session_names_canonical" in out


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

    rc = RulesCommand().grep("COACH-SESSION-NAMING-0001")
    assert rc == 0
    out = capsys.readouterr().out
    # The canonical rule is surfaced even though the pattern is the alias.
    assert "coach.session.canonical-session-name" in out


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


# =============================================================================
# Issue #494 — atdd rules disposition / archetype / suppressions
# =============================================================================
# These three subcommands extend the discovery surface from #493 with the
# enumerate-by-attribute view (per spec §5.7). The fixture registry already
# carries three repo.* rules (all walker-set to ``strict``) plus the full
# toolkit-convention registry, so the assertions key off the fixture rules
# while still tolerating the toolkit's own catalog growing over time.

# ---------------------------------------------------------------------------
# atdd rules disposition <strict|suppress-and-clean|advisory|documentation-only>
#   acc:discover-and-decommission:L002-UNIT-001
# ---------------------------------------------------------------------------
def test_rules_disposition_strict_lists_repo_and_toolkit_rules(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``disposition strict`` surfaces every strict rule across both registries.

    Repo rules are uniformly strict per substrate v12 §2 (walker-set), so
    every fixture repo rule must appear; toolkit strict rules also appear
    because the merged registry is one stream.
    """
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().disposition("strict")
    assert rc == 0
    out = capsys.readouterr().out
    # All three fixture repo rules — uniformly strict per §2.
    assert "repo.govern-lifecycle.D010-acc-unit-001" in out
    assert "repo.foo-wagon.D001-acc-http-007" in out
    assert "repo.0001-self-compliance-validate.acc-idempotent-on-retry" in out


def test_rules_disposition_strict_line_carries_id_archetype_severity_description(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Each output line shows rule-id + archetype + severity + description.

    Per acc:L002-UNIT-001: each line shows enough context to be
    self-explanatory at a glance — rule-id, archetype, severity, and
    the one-line description.
    """
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().disposition("strict")
    assert rc == 0
    out = capsys.readouterr().out
    # The fixture repo rule's line carries the four required fields.
    matching = [
        line for line in out.splitlines()
        if "repo.govern-lifecycle.D010-acc-unit-001" in line
    ]
    assert matching, "fixture repo rule missing from disposition strict output"
    line = matching[0]
    # Archetype tag.
    assert "repo" in line
    # Severity (walker constant: 4).
    assert "sev=4" in line
    # Description (purpose) substring.
    assert "theme_map" in line


def test_rules_disposition_suppress_and_clean_returns_toolkit_only(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``disposition suppress-and-clean`` lists toolkit rules only.

    Per substrate v12 §2 repo rules are uniformly strict; non-strict
    dispositions must NOT include any ``repo.*`` rule.
    """
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().disposition("suppress-and-clean")
    # Either zero (when toolkit has at least one) or non-zero (empty); but
    # the load-bearing assertion is the registry purity.
    out = capsys.readouterr().out
    assert "repo." not in out, "repo.* rules must not appear under non-strict dispositions"


def test_rules_disposition_advisory_returns_toolkit_only(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Same purity invariant as suppress-and-clean for advisory."""
    from atdd.coach.commands.rules import RulesCommand

    RulesCommand().disposition("advisory")
    out = capsys.readouterr().out
    assert "repo." not in out


def test_rules_disposition_documentation_only_returns_toolkit_only(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Same purity invariant for documentation-only."""
    from atdd.coach.commands.rules import RulesCommand

    RulesCommand().disposition("documentation-only")
    out = capsys.readouterr().out
    assert "repo." not in out


def test_rules_disposition_invalid_value_returns_nonzero_with_options(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """An unknown disposition exits 1 and surfaces the four valid options."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().disposition("nonsense")
    assert rc == 1
    err = capsys.readouterr().err
    # Lists each valid option so the operator sees the vocabulary.
    assert "strict" in err
    assert "suppress-and-clean" in err
    assert "advisory" in err
    assert "documentation-only" in err


def test_rules_disposition_json_format(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``--format json`` emits a list of rule metadata dicts."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().disposition("strict", format="json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    rule_ids = {entry["rule_id"] for entry in payload}
    assert "repo.govern-lifecycle.D010-acc-unit-001" in rule_ids
    # Every entry has disposition='strict'.
    assert all(entry["disposition"] == "strict" for entry in payload)


# ---------------------------------------------------------------------------
# atdd rules archetype <coder|coach|tester|planner|repo>
#   acc:discover-and-decommission:L002-UNIT-002
# ---------------------------------------------------------------------------
def test_rules_archetype_repo_lists_every_substrate_rule(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``archetype repo`` lists every substrate-derived rule (per substrate v12)."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().archetype("repo")
    assert rc == 0
    out = capsys.readouterr().out
    # All three fixture repo rules.
    assert "repo.govern-lifecycle.D010-acc-unit-001" in out
    assert "repo.foo-wagon.D001-acc-http-007" in out
    assert "repo.0001-self-compliance-validate.acc-idempotent-on-retry" in out
    # No toolkit rule (e.g., coach.*) leaks in.
    assert "coach.session.canonical-session-name" not in out


def test_rules_archetype_repo_output_sorted_by_rule_id(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """Output is sorted by rule-id within an archetype (stable diffing)."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().archetype("repo")
    assert rc == 0
    out = capsys.readouterr().out
    # Find positions of the three fixture rule-ids; they must be ordered
    # ascending by string.
    ids = [
        "repo.0001-self-compliance-validate.acc-idempotent-on-retry",
        "repo.foo-wagon.D001-acc-http-007",
        "repo.govern-lifecycle.D010-acc-unit-001",
    ]
    positions = [out.index(rid) for rid in ids]
    assert positions == sorted(positions), (
        f"archetype repo output not sorted: positions={positions}"
    )


def test_rules_archetype_coach_excludes_repo_rules(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``archetype coach`` returns coach toolkit rules only — no repo leakage."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().archetype("coach")
    assert rc == 0
    out = capsys.readouterr().out
    # No repo.* rule in coach archetype.
    assert "repo." not in out
    # A known coach toolkit rule appears.
    assert "coach.session.canonical-session-name" in out


def test_rules_archetype_coder_returns_only_coder_rules(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``archetype coder`` returns only rules whose id starts with ``coder.``."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().archetype("coder")
    assert rc == 0
    out = capsys.readouterr().out
    # A real coder rule we know exists.
    assert "coder.logging.coach-silent-swallow" in out
    # Other archetypes don't leak.
    assert "coach." not in out.replace("coach-silent-swallow", "")
    assert "tester." not in out
    assert "planner." not in out


def test_rules_archetype_tester_excludes_other_archetypes(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``archetype tester`` returns only tester rules."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().archetype("tester")
    assert rc == 0
    out = capsys.readouterr().out
    # Other archetypes absent from each line.
    for line in out.splitlines():
        if "—" in line:  # rule lines carry an em-dash separator
            # Lines under archetype=tester start with tester. rule-id.
            stripped = line.lstrip()
            if stripped and not stripped.startswith("Total:"):
                assert stripped.startswith("tester."), f"non-tester rule in archetype tester: {line!r}"


def test_rules_archetype_planner_excludes_other_archetypes(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``archetype planner`` returns only planner rules."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().archetype("planner")
    assert rc == 0
    out = capsys.readouterr().out
    for line in out.splitlines():
        if "—" in line and not line.lstrip().startswith("Total:"):
            stripped = line.lstrip()
            if stripped:
                assert stripped.startswith("planner."), (
                    f"non-planner rule in archetype planner: {line!r}"
                )


def test_rules_archetype_unknown_value_returns_nonzero_with_options(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """An unknown archetype exits 1 and surfaces the five valid options."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().archetype("frontend")
    assert rc == 1
    err = capsys.readouterr().err
    for option in ("coder", "coach", "tester", "planner", "repo"):
        assert option in err, f"missing valid archetype {option!r} in error message"


def test_rules_archetype_json_format(
    seeded_registry: Path, capsys: pytest.CaptureFixture[str]
):
    """``--format json`` emits a list of rule metadata dicts for the archetype."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().archetype("repo", format="json")
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload, list)
    assert len(payload) == 3
    assert {entry["rule_id"] for entry in payload} == {
        "repo.govern-lifecycle.D010-acc-unit-001",
        "repo.foo-wagon.D001-acc-http-007",
        "repo.0001-self-compliance-validate.acc-idempotent-on-retry",
    }


# ---------------------------------------------------------------------------
# atdd rules suppressions [--stale-only] [--rule <id>]
#   acc:discover-and-decommission:L002-UNIT-003
# ---------------------------------------------------------------------------
# Build the suppression marker token at runtime so this *source* file does
# not itself trigger the suppression scanner / stale-suppression validator
# when CI walks the repo. The written tmp_path files reconstruct the full
# literal so the scanner under test still sees a real marker.
_SUPPRESS_TOKEN = "atdd:" + "suppress"


def _seed_suppression_files(tmp_path: Path) -> None:
    """Plant a mix of active, stale, and repo-rule markers under *tmp_path*.

    Layout:
      a.py      — active marker (UNTIL future)
      b.py      — bare marker (no UNTIL — never stale)
      stale.py  — stale marker (UNTIL past)
      repo.py   — marker referencing a repo.* rule (substrate-unsuppressible)
    """
    (tmp_path / "a.py").write_text(
        f"x = 1  # {_SUPPRESS_TOKEN}(coder.logging.coach-silent-swallow) UNTIL=2099-01-01\n",
        encoding="utf-8",
    )
    (tmp_path / "b.py").write_text(
        f"y = 2  # {_SUPPRESS_TOKEN}(coder.logging.no-print-calls-in)\n",
        encoding="utf-8",
    )
    (tmp_path / "stale.py").write_text(
        f"z = 3  # {_SUPPRESS_TOKEN}(coder.logging.coach-silent-swallow) UNTIL=2020-01-01\n",
        encoding="utf-8",
    )
    (tmp_path / "repo.py").write_text(
        f"w = 4  # {_SUPPRESS_TOKEN}(repo.foo-wagon.D001-acc-http-007) UNTIL=2099-01-01\n",
        encoding="utf-8",
    )


def test_rules_suppressions_lists_all_active_markers(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """``atdd rules suppressions`` lists every active marker (file, line, rule, UNTIL)."""
    from atdd.coach.commands.rules import RulesCommand

    _seed_suppression_files(tmp_path)
    rc = RulesCommand().suppressions(roots=[tmp_path])
    assert rc == 0
    out = capsys.readouterr().out
    # All four files surface.
    assert "a.py" in out
    assert "b.py" in out
    assert "stale.py" in out
    assert "repo.py" in out
    # Each line shows rule-id + line number.
    assert "coder.logging.coach-silent-swallow" in out
    assert "coder.logging.no-print-calls-in" in out
    assert "repo.foo-wagon.D001-acc-http-007" in out
    # UNTIL date for the dated marker is rendered.
    assert "2099-01-01" in out


def test_rules_suppressions_stale_only_filters_to_past_until(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """``--stale-only`` filters to markers whose UNTIL date has passed."""
    from atdd.coach.commands.rules import RulesCommand

    _seed_suppression_files(tmp_path)
    rc = RulesCommand().suppressions(roots=[tmp_path], stale_only=True)
    assert rc == 0
    out = capsys.readouterr().out
    # Only the stale marker survives.
    assert "stale.py" in out
    assert "2020-01-01" in out
    # Active and bare markers are filtered out.
    assert "a.py" not in out
    assert "b.py" not in out


def test_rules_suppressions_rule_filter_narrows_to_one_rule(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """``--rule <id>`` filters to markers for the given rule-id only."""
    from atdd.coach.commands.rules import RulesCommand

    _seed_suppression_files(tmp_path)
    rc = RulesCommand().suppressions(
        roots=[tmp_path],
        rule_id="coder.logging.no-print-calls-in",
    )
    assert rc == 0
    out = capsys.readouterr().out
    # Only b.py (the matching marker) appears.
    assert "b.py" in out
    assert "coder.logging.no-print-calls-in" in out
    # Other markers do not.
    assert "a.py" not in out
    assert "stale.py" not in out
    assert "repo.py" not in out


def test_rules_suppressions_warns_on_repo_rule_marker(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Markers referencing ``repo.*`` rules surface as warnings.

    Per substrate v12 §2 repo rules are uniformly strict and unsuppressible
    — the marker is silently ignored by the gate, so the CLI is the only
    place an operator can see the misapplication.
    """
    from atdd.coach.commands.rules import RulesCommand

    _seed_suppression_files(tmp_path)
    RulesCommand().suppressions(roots=[tmp_path])
    captured = capsys.readouterr()
    # The warning surfaces the offending rule-id and a clear "unsuppressible"
    # phrase. Stderr is the right channel — operators piping stdout into a
    # report still get the alert.
    combined = captured.out + captured.err
    assert "repo.foo-wagon.D001-acc-http-007" in combined
    assert any(
        token in combined.lower()
        for token in ("warning", "unsuppressible", "ignored")
    ), "repo-rule marker did not surface as a warning"


def test_rules_suppressions_empty_repo_exits_zero(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """Empty result (no markers) still exits zero — distinct from grep."""
    from atdd.coach.commands.rules import RulesCommand

    rc = RulesCommand().suppressions(roots=[tmp_path])
    assert rc == 0


def test_rules_suppressions_json_format(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
):
    """``--format json`` emits a structured list of marker dicts."""
    from atdd.coach.commands.rules import RulesCommand

    _seed_suppression_files(tmp_path)
    rc = RulesCommand().suppressions(roots=[tmp_path], format="json")
    assert rc == 0
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert isinstance(payload, list)
    # Each entry has the four required fields per spec §5.7.
    for entry in payload:
        assert set(entry).issuperset({"file_path", "line", "rule_id", "until"})
    # All four markers appear.
    assert len(payload) == 4
    rule_ids = {entry["rule_id"] for entry in payload}
    assert "repo.foo-wagon.D001-acc-http-007" in rule_ids
