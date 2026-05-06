# URN: urn:atdd:test:coach:utils:rule_binding:security_walker
# Issue: #422

"""Unit tests for the security-rule walker (substrate spec v12 §4.5 / §5.4 / §7.4).

Coverage:

* Rule-ID derivation from security URNs (§5.4).
* RuleMetadata field population for resolved abuse_cases:
  severity mapping (low→2, medium→3, high→4, critical→5; missing→3),
  description ``<name> — <threat>``, fix_hint = mitigation, walker-set
  disposition=strict, validator literal, security/feature/bound URN
  discriminators, phase propagation from bound acceptance.
* Two-place split (§7.4): unresolved acceptance_ref does NOT enter the
  registry; ``find_unresolved_security_refs`` surfaces it.
* Severity passthrough for missing/unknown values (defaults to medium).
* Deterministic ordering for snapshot tests.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent
from typing import Optional

import pytest


pytestmark = [pytest.mark.platform]


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
    return tmp_path


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dedent(body).lstrip(), encoding="utf-8")
    return path


def _author_session_management_feature(
    repo: Path, *, severity: Optional[str] = "high", abuse_id: str = "THREAT-001"
) -> Path:
    """Write a feature.yaml with one abuse_case under plan/auth/features/."""
    severity_line = f"severity: {severity}" if severity is not None else ""
    return _write(
        repo / "plan" / "auth" / "features" / "session_management.yaml",
        f"""
        urn: "feature:auth:session-management"
        title: "Session management feature"
        security:
          abuse_cases:
            - id: "{abuse_id}"
              name: "Session Hijacking"
              threat: "Attacker steals session token via XSS"
              mitigation: "HttpOnly cookies, CSP headers"
              {severity_line}
              acceptance_ref: "acc:auth:D001-UNIT-001-session-protection"
        """,
    )


def _author_bound_wmbt(repo: Path) -> Path:
    """Write a WMBT acceptance the abuse_case's acceptance_ref points at."""
    return _write(
        repo / "plan" / "auth" / "D001.yaml",
        """
        urn: "wmbt:auth:D001"
        step: define
        direction: minimize
        dimension: quantity
        object_of_control: stolen-session-tokens
        context_clarifier: ctx
        lens: functional.security
        statement: "minimize stolen session tokens"
        acceptances:
          - identity:
              urn: "acc:auth:D001-UNIT-001-session-protection"
              id: "AC-UNIT-001"
              purpose: "Session tokens are not exfiltrable via XSS"
              phase: "GREEN"
            harness:
              type: unit
              category: backend
            given:
              abstract: ["session cookie has HttpOnly flag"]
            when:
              abstract: "an injected script reads document.cookie"
            then:
              abstract: ["the cookie value is unavailable to scripts"]
        """,
    )


# ---------------------------------------------------------------------------
# Derivation
# ---------------------------------------------------------------------------
def test_derive_security_rule_id_matches_spec_example():
    """``security:auth:session-management:001`` → ``repo.auth.session-management-security-001``."""
    from atdd.coach.utils.rule_binding import derive_security_rule_id

    rule_id = derive_security_rule_id("security:auth:session-management:001")
    assert rule_id == "repo.auth.session-management-security-001"


def test_derive_security_rule_id_rejects_malformed_urn():
    from atdd.coach.utils.rule_binding import (
        RepoYamlValidationError,
        derive_security_rule_id,
    )

    with pytest.raises(RepoYamlValidationError):
        derive_security_rule_id("security:auth:session-management")  # 3 segments


# ---------------------------------------------------------------------------
# Resolved-rule walker
# ---------------------------------------------------------------------------
def test_walker_emits_resolved_security_rule(fixture_repo: Path):
    """Fixture with one resolved abuse_case yields one RuleMetadata."""
    from atdd.coach.utils.rule_binding import find_repo_security_rules

    _author_session_management_feature(fixture_repo)
    _author_bound_wmbt(fixture_repo)

    results = find_repo_security_rules(fixture_repo)
    assert len(results) == 1
    src, meta = results[0]
    assert src.name == "session_management.yaml"
    assert meta.rule_id == "repo.auth.session-management-security-001"


def test_walker_populates_rule_metadata_per_spec_example(fixture_repo: Path):
    """RuleMetadata fields match the spec §6 sample failure block."""
    from atdd.coach.utils.rule_binding import find_repo_security_rules

    _author_session_management_feature(fixture_repo, severity="high")
    _author_bound_wmbt(fixture_repo)

    results = find_repo_security_rules(fixture_repo)
    _, meta = results[0]

    # Walker-set constants per §4.4.
    assert meta.disposition == "strict"
    assert meta.validator == (
        "test_security_ref_binding::test_acceptance_ref_resolves_and_passes"
    )
    # Severity mapping: high → 4 (§4.5 issue spec).
    assert meta.severity == 4
    # Description = "<name> — <threat>" per §6 sample.
    assert meta.description == (
        "Session Hijacking — Attacker steals session token via XSS"
    )
    # fix_hint = mitigation per §6 sample.
    assert meta.fix_hint == "HttpOnly cookies, CSP headers"
    # Discriminator URNs.
    assert meta.security_urn == "security:auth:session-management:001"
    assert meta.feature_urn == "feature:auth:session-management"
    assert meta.bound_acceptance_urn == "acc:auth:D001-UNIT-001-session-protection"
    # Phase propagated from bound acceptance.
    assert meta.phase == "GREEN"


@pytest.mark.parametrize(
    "yaml_severity,expected_int",
    [
        ("low", 2),
        ("medium", 3),
        ("high", 4),
        ("critical", 5),
        (None, 3),  # missing → medium default
        ("unknown-tier", 3),  # unrecognized → medium default
    ],
)
def test_walker_maps_severity_per_issue_spec(
    fixture_repo: Path, yaml_severity, expected_int
):
    """Severity mapping per issue #422 / spec §4.5."""
    from atdd.coach.utils.rule_binding import find_repo_security_rules

    _author_session_management_feature(fixture_repo, severity=yaml_severity)
    _author_bound_wmbt(fixture_repo)

    results = find_repo_security_rules(fixture_repo)
    assert len(results) == 1
    _, meta = results[0]
    assert meta.severity == expected_int


def test_walker_skips_unresolved_acceptance_ref(fixture_repo: Path):
    """Unresolved acceptance_ref does NOT enter the registry (§7.4 split)."""
    from atdd.coach.utils.rule_binding import (
        find_repo_security_rules,
        find_unresolved_security_refs,
    )

    # Author the feature.yaml WITHOUT the bound WMBT — acceptance_ref is broken.
    _author_session_management_feature(fixture_repo)
    # No _author_bound_wmbt call.

    results = find_repo_security_rules(fixture_repo)
    assert results == []  # registry is silent

    unresolved = find_unresolved_security_refs(fixture_repo)
    assert len(unresolved) == 1
    ref = unresolved[0]
    assert ref.security_urn == "security:auth:session-management:001"
    assert ref.feature_urn == "feature:auth:session-management"
    assert ref.acceptance_ref == "acc:auth:D001-UNIT-001-session-protection"


def test_walker_skips_when_wmbt_exists_but_acceptance_block_missing(fixture_repo: Path):
    """A parent file that exists but lacks the matching identity.urn is unresolved."""
    from atdd.coach.utils.rule_binding import (
        find_repo_security_rules,
        find_unresolved_security_refs,
    )

    _author_session_management_feature(fixture_repo)
    # Parent WMBT exists but declares a DIFFERENT acceptance URN.
    _write(
        fixture_repo / "plan" / "auth" / "D001.yaml",
        """
        urn: "wmbt:auth:D001"
        step: define
        direction: minimize
        dimension: quantity
        object_of_control: thing
        context_clarifier: ctx
        lens: functional.security
        statement: "stmt"
        acceptances:
          - identity:
              urn: "acc:auth:D001-UNIT-002-different-acceptance"
              purpose: "different"
              phase: "GREEN"
            harness: { type: unit }
        """,
    )

    assert find_repo_security_rules(fixture_repo) == []
    unresolved = find_unresolved_security_refs(fixture_repo)
    assert len(unresolved) == 1


def test_walker_orders_results_deterministically(fixture_repo: Path):
    """Results are ordered by feature path then rule_id (snapshot stability)."""
    from atdd.coach.utils.rule_binding import find_repo_security_rules

    # Two features each with one resolved abuse_case.
    _author_bound_wmbt(fixture_repo)
    _write(
        fixture_repo / "plan" / "auth" / "features" / "a_feature.yaml",
        """
        urn: "feature:auth:a-feature"
        security:
          abuse_cases:
            - id: "T-001"
              name: "Threat A"
              threat: "scenario A"
              mitigation: "fix A"
              severity: low
              acceptance_ref: "acc:auth:D001-UNIT-001-session-protection"
        """,
    )
    _write(
        fixture_repo / "plan" / "auth" / "features" / "z_feature.yaml",
        """
        urn: "feature:auth:z-feature"
        security:
          abuse_cases:
            - id: "T-001"
              name: "Threat Z"
              threat: "scenario Z"
              mitigation: "fix Z"
              severity: low
              acceptance_ref: "acc:auth:D001-UNIT-001-session-protection"
        """,
    )

    results = find_repo_security_rules(fixture_repo)
    assert len(results) == 2
    paths = [str(p) for p, _ in results]
    assert paths == sorted(paths)
