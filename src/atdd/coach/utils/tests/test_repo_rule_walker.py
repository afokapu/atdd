# URN: urn:atdd:test:coach:utils:rule_binding:repo_walker
# Issue: #408

"""Unit tests for the repo-rule walker (substrate spec v12 §3.3 / §4.2 / §4.3 / §4.4).

Coverage:

* Rule-ID derivation from WMBT acceptance URNs (harness lowering, slug drop).
* Rule-ID derivation from train acceptance URNs (free-form slug preserved).
* RuleMetadata field population (severity=4, disposition=strict, fix_hint
  composition, phase passthrough, acceptance/wmbt/train URN discriminators).
* Walker invariant skip (missing phase, missing harness+signal).
* Loud failure on declared ``disposition:`` and on top-level acceptance ``id:``.
* Live integration: the walker finds at least one rule under the toolkit's
  own ``plan/`` directory.
"""

from __future__ import annotations

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


@pytest.fixture
def fixture_repo(tmp_path: Path) -> Path:
    """Create a stand-in consumer repo rooted at ``tmp_path``."""
    (tmp_path / "plan").mkdir()
    (tmp_path / "plan" / "_trains").mkdir()
    return tmp_path


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body).lstrip(), encoding="utf-8")
    return path


# WMBT body shared across multiple tests so each YAML is < 25 lines.
_WMBT_D010 = """
    urn: "wmbt:govern-lifecycle:D010"
    step: "define"
    direction: "minimize"
    dimension: "quantity"
    object_of_control: "duplicated-hardcoded-theme-map-dicts-across-modules"
    context_clarifier: "fixture file mirroring the live D010.yaml"
    lens: "functional.sustainability"
    statement: "minimize duplicated hardcoded theme_map literals"
    acceptances:
      - identity:
          urn: "acc:govern-lifecycle:D010-UNIT-001-single-source-theme-map-helper"
          id: "AC-UNIT-001"
          purpose: "A single get_theme_map(config) helper replaces every hardcoded theme_map dict in the codebase"
          phase: "GREEN"
        harness:
          type: "unit"
          category: "backend"
        given:
          abstract: ["coach/utils/theme_map.py exposes get_theme_map(config) returning merged defaults + overrides"]
        when:
          abstract: "A grep for hardcoded theme_map dict literals runs across src/atdd"
        then:
          abstract:
            - "No theme_map dict literal appears outside coach/utils/theme_map.py"
            - "inventory.py, registry.py, and test_train_validation.py import and call get_theme_map"
            - "The helper is the single source of truth for the digit-to-theme mapping"
        signal:
          metric: "hardcoded_theme_map_literal_count"
          threshold: 0
        metadata:
          author: "atdd:self-compliance"
          created: "2026-04-17"
"""


# ---------------------------------------------------------------------------
# WMBT-shape derivation
# ---------------------------------------------------------------------------
def test_walker_derives_rule_id_from_wmbt_acceptance_urn(fixture_repo: Path):
    """WMBT acceptance URN derives to ``repo.<wagon>.<WMBT>-acc-<harness>-<seq>``.

    Spec v12 §3.3 derivation: harness code lowered, trailing slug dropped,
    WMBT step-letter prefix preserved verbatim.
    """
    from atdd.coach.utils.rule_binding import find_repo_rules

    _write(fixture_repo / "plan" / "govern_lifecycle" / "D010.yaml", _WMBT_D010)

    results = find_repo_rules(fixture_repo)
    assert len(results) == 1
    src, meta = results[0]
    assert src.name == "D010.yaml"
    assert meta.rule_id == "repo.govern-lifecycle.D010-acc-unit-001"


def test_walker_populates_rule_metadata_from_d010(fixture_repo: Path):
    """RuleMetadata population matches §4.2 acceptance table for the D010 fixture."""
    from atdd.coach.utils.rule_binding import bind_rule, clear_cache

    _write(fixture_repo / "plan" / "govern_lifecycle" / "D010.yaml", _WMBT_D010)
    clear_cache(override_repo_root=fixture_repo)

    meta = bind_rule("repo.govern-lifecycle.D010-acc-unit-001")
    # Walker-set constants (§4.2 / §4.4).
    assert meta.severity == 4
    assert meta.disposition == "strict"
    assert meta.recipe is None  # acceptance rules carry no recipe pointer
    # Identity passthrough.
    assert meta.description == (
        "A single get_theme_map(config) helper replaces every hardcoded "
        "theme_map dict in the codebase"
    )
    assert meta.phase == "GREEN"
    # Discriminator URNs.
    assert meta.acceptance_urn == (
        "acc:govern-lifecycle:D010-UNIT-001-single-source-theme-map-helper"
    )
    assert meta.wmbt_urn == "wmbt:govern-lifecycle:D010"
    assert meta.train_urn is None
    # Context fields.
    assert meta.harness_type == "unit"
    assert meta.harness_category == "backend"
    assert meta.signal_metric == "hardcoded_theme_map_literal_count"
    assert meta.signal_threshold == "0"
    assert meta.author == "atdd:self-compliance"
    assert meta.created == "2026-04-17"


def test_walker_composes_fix_hint_from_then_abstract(fixture_repo: Path):
    """``fix_hint`` is ``then.abstract`` items joined with ``"; "`` (§4.2)."""
    from atdd.coach.utils.rule_binding import bind_rule, clear_cache

    _write(fixture_repo / "plan" / "govern_lifecycle" / "D010.yaml", _WMBT_D010)
    clear_cache(override_repo_root=fixture_repo)

    meta = bind_rule("repo.govern-lifecycle.D010-acc-unit-001")
    assert meta.fix_hint == (
        "No theme_map dict literal appears outside coach/utils/theme_map.py; "
        "inventory.py, registry.py, and test_train_validation.py import and call get_theme_map; "
        "The helper is the single source of truth for the digit-to-theme mapping"
    )


def test_walker_drops_trailing_slug_from_wmbt_urn(fixture_repo: Path):
    """Trailing slug on WMBT acc URN is dropped from rule-id; preserved on metadata."""
    from atdd.coach.utils.rule_binding import find_repo_rules

    _write(
        fixture_repo / "plan" / "foo_wagon" / "D001.yaml",
        """
        urn: "wmbt:foo-wagon:D001"
        step: define
        direction: minimize
        dimension: quantity
        object_of_control: thing
        context_clarifier: ctx
        lens: functional.sustainability
        statement: stmt
        acceptances:
          - identity:
              urn: "acc:foo-wagon:D001-HTTP-007-very-long-readability-slug-here"
              purpose: "purpose"
              phase: "RED"
            harness: { type: http }
        """,
    )

    results = find_repo_rules(fixture_repo)
    assert len(results) == 1
    _, meta = results[0]
    assert meta.rule_id == "repo.foo-wagon.D001-acc-http-007"
    assert meta.acceptance_urn.endswith("very-long-readability-slug-here")


# ---------------------------------------------------------------------------
# Train-shape derivation
# ---------------------------------------------------------------------------
_TRAIN_FIXTURE = """
    train_id: "0001-self-compliance-validate"
    title: "Self-compliance validation train"
    description: "Fixture train carrying acceptances for the walker test."
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
          purpose: "Re-running the train with the same idempotency key produces no duplicate side effects"
          phase: "SMOKE"
        harness:
          type: "e2e"
        signal:
          metric: "duplicate_side_effects_on_retry"
          threshold: 0
"""


def test_walker_derives_rule_from_train_fixture(fixture_repo: Path):
    """Train acceptance URN derives to ``repo.<train-id>.acc-<slug>``.

    Per spec v12 §3.3 second derivation row. Acceptance criterion for #408
    relaxed from "real train YAML" to "FIXTURE train YAML" — see issue body.
    """
    from atdd.coach.utils.rule_binding import bind_rule, clear_cache

    _write(
        fixture_repo / "plan" / "_trains" / "0001-self-compliance-validate.yaml",
        _TRAIN_FIXTURE,
    )
    clear_cache(override_repo_root=fixture_repo)

    meta = bind_rule("repo.0001-self-compliance-validate.acc-idempotent-on-retry")
    assert meta.rule_id == "repo.0001-self-compliance-validate.acc-idempotent-on-retry"
    assert meta.severity == 4
    assert meta.disposition == "strict"
    assert meta.phase == "SMOKE"
    assert meta.train_urn == "train:0001-self-compliance-validate"
    assert meta.wmbt_urn is None
    assert meta.harness_type == "e2e"
    assert meta.signal_metric == "duplicate_side_effects_on_retry"


# ---------------------------------------------------------------------------
# Walker invariants (§4.3) — silent skip
# ---------------------------------------------------------------------------
def test_walker_skips_acceptance_missing_phase(fixture_repo: Path):
    """An acceptance without ``identity.phase`` is silently dropped."""
    from atdd.coach.utils.rule_binding import find_repo_rules

    _write(
        fixture_repo / "plan" / "wagon" / "D001.yaml",
        """
        urn: "wmbt:wagon:D001"
        acceptances:
          - identity:
              urn: "acc:wagon:D001-UNIT-001"
              purpose: "missing phase"
            harness: { type: unit }
        """,
    )

    assert find_repo_rules(fixture_repo) == []


def test_walker_skips_acceptance_missing_harness_and_signal(fixture_repo: Path):
    """Acceptance with neither ``harness.type`` nor ``signal.metric+threshold`` skipped."""
    from atdd.coach.utils.rule_binding import find_repo_rules

    _write(
        fixture_repo / "plan" / "wagon" / "D002.yaml",
        """
        urn: "wmbt:wagon:D002"
        acceptances:
          - identity:
              urn: "acc:wagon:D002-UNIT-001"
              purpose: "no harness or signal"
              phase: "GREEN"
        """,
    )

    assert find_repo_rules(fixture_repo) == []


def test_walker_accepts_signal_only_acceptance(fixture_repo: Path):
    """Signal-mode acceptance (no harness.type) still produces a rule."""
    from atdd.coach.utils.rule_binding import find_repo_rules

    _write(
        fixture_repo / "plan" / "wagon" / "D003.yaml",
        """
        urn: "wmbt:wagon:D003"
        acceptances:
          - identity:
              urn: "acc:wagon:D003-METRIC-001"
              purpose: "signal-only"
              phase: "REFACTOR"
            signal:
              metric: "thing_count"
              threshold: 0
        """,
    )

    results = find_repo_rules(fixture_repo)
    assert len(results) == 1
    _, meta = results[0]
    assert meta.harness_type is None
    assert meta.signal_metric == "thing_count"
    assert meta.validator == "test_metric_runner::test_metric_threshold_satisfied"


# ---------------------------------------------------------------------------
# Loud failures (§4.4 disposition; §3.3 forbidden id:)
# ---------------------------------------------------------------------------
def test_walker_rejects_disposition_field_in_repo_yaml(fixture_repo: Path):
    """Repo YAML may not declare ``disposition:`` (walker sets it per §4.4)."""
    from atdd.coach.utils.rule_binding import RepoYamlValidationError, find_repo_rules

    bad = _write(
        fixture_repo / "plan" / "wagon" / "D001.yaml",
        """
        urn: "wmbt:wagon:D001"
        acceptances:
          - identity:
              urn: "acc:wagon:D001-UNIT-001"
              purpose: "p"
              phase: "GREEN"
            harness: { type: unit }
            disposition: "advisory"
        """,
    )

    with pytest.raises(RepoYamlValidationError) as exc:
        find_repo_rules(fixture_repo)
    msg = str(exc.value)
    assert str(bad) in msg
    assert "disposition" in msg


def test_walker_rejects_top_level_id_in_acceptance_block(fixture_repo: Path):
    """A literal top-level ``id:`` on an acceptance entry fails registry build."""
    from atdd.coach.utils.rule_binding import RepoYamlValidationError, find_repo_rules

    bad = _write(
        fixture_repo / "plan" / "wagon" / "D001.yaml",
        """
        urn: "wmbt:wagon:D001"
        acceptances:
          - id: "manually-set-rule-id"
            identity:
              urn: "acc:wagon:D001-UNIT-001"
              purpose: "p"
              phase: "GREEN"
            harness: { type: unit }
        """,
    )

    with pytest.raises(RepoYamlValidationError) as exc:
        find_repo_rules(fixture_repo)
    msg = str(exc.value)
    assert str(bad) in msg
    assert "id" in msg


def test_walker_skips_acceptance_with_malformed_urn(fixture_repo: Path):
    """An acceptance whose URN fails URNGrammar.PATTERNS['acc'] is skipped.

    Per the spec issue text: "failure of (a) [URN pattern] is a parent-graph
    problem caught by `atdd repo validate`" — so the walker silently skips
    the offending acceptance instead of failing the whole registry build.
    """
    from atdd.coach.utils.rule_binding import find_repo_rules

    _write(
        fixture_repo / "plan" / "wagon" / "D001.yaml",
        """
        urn: "wmbt:wagon:D001"
        acceptances:
          - identity:
              urn: "acc:wagon:D001-NOTAHARNESS-001"
              purpose: "malformed"
              phase: "GREEN"
            harness: { type: unit }
        """,
    )

    assert find_repo_rules(fixture_repo) == []


# ---------------------------------------------------------------------------
# Integration against toolkit's own plan/
# ---------------------------------------------------------------------------
def test_walker_finds_rules_in_toolkit_self_plan():
    """Pointing the walker at the toolkit checkout produces a non-empty registry.

    Smoke check that ``find_repo_rules`` works against real ATDD plan/ data
    rather than only fixtures. Asserts presence of both WMBT-derived rules
    and at least one rule per known wagon directory currently shipping
    structured acceptances.
    """
    from atdd.coach.utils.repo import find_repo_root
    from atdd.coach.utils.rule_binding import find_repo_rules

    repo_root = find_repo_root()
    plan_dir = repo_root / "plan"
    if not plan_dir.is_dir():
        pytest.skip("no plan/ in this checkout")

    results = find_repo_rules(repo_root)
    assert len(results) > 0, "walker found no rules under live plan/"
    rule_ids = {meta.rule_id for _src, meta in results}
    # Every derived rule starts with the repo archetype (§3.1 / §3.3).
    assert all(rid.startswith("repo.") for rid in rule_ids)
