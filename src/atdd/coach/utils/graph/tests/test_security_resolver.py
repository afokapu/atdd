# URN: test:coach:graph_security_resolver:abuse_cases
"""
Acceptance tests for SecurityResolver (#419).

Covers:
  - Threat-seq derivation from abuse_case.id (THREAT-1 -> 001 etc.)
  - Strict id validation: missing/malformed/numeric-tail-too-large rejected.
  - find_declarations() returns one URNDeclaration per abuse_case keyed
    by source_path with context "abuse_case".
  - URN format security:<wagon>:<feature>:<NNN>.
  - URNResolution.metadata exposes abuse_case fields (id, name, threat,
    mitigation, severity, acceptance_ref) verbatim from feature.yaml.
  - find_all_declarations(['security']) on a fixture plan/ with two
    features × three abuse_cases each returns six URNDeclaration entries.
"""

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from atdd.coach.utils.graph.resolver import (
    ResolverRegistry,
    SecurityResolver,
    URNDeclaration,
)


# ---------------------------------------------------------------------------
# Fixture builders
# ---------------------------------------------------------------------------


def _write_feature(
    plan_dir: Path,
    wagon_slug: str,
    feature_slug: str,
    abuse_cases_yaml: str,
) -> Path:
    """Write a minimal plan/<wagon>/features/<feature>.yaml with abuse_cases.

    ``abuse_cases_yaml`` is the de-dented body of the ``abuse_cases`` list;
    each line is re-indented by 4 spaces so it sits under ``abuse_cases:``.
    """
    wagon_dir = plan_dir / wagon_slug.replace("-", "_")
    features_dir = wagon_dir / "features"
    features_dir.mkdir(parents=True, exist_ok=True)
    feature_file = features_dir / f"{feature_slug.replace('-', '_')}.yaml"
    indented_abuse = "\n".join(
        ("    " + line) if line.strip() else line
        for line in abuse_cases_yaml.splitlines()
    )
    body = dedent(
        f"""\
        urn: "feature:{wagon_slug}:{feature_slug}"
        wagon: "wagon:{wagon_slug}"
        description: "Fixture feature for SecurityResolver tests"
        sizing:
          wmbts: 0
          footprint_score: 1
          footprint_size: "S"
        wmbts: []
        components:
          backend:
            presentation: []
            application: []
            domain: []
            integration: []
        security:
          abuse_cases:
        """
    )
    body += indented_abuse + "\n"
    feature_file.write_text(body)
    return feature_file


# ---------------------------------------------------------------------------
# derive_threat_seq
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "abuse_id,expected_seq",
    [
        ("THREAT-001", "001"),
        ("THREAT-1", "001"),
        ("THREAT-42", "042"),
        ("THREAT-999", "999"),
        ("ABUSE-007", "007"),
        ("INJ-SQL-12", "012"),  # alphabetic prefix may contain hyphens/digits
    ],
)
def test_derive_threat_seq_zero_pads(abuse_id, expected_seq):
    """Valid ids zero-pad the trailing number to three digits."""
    seq, err = SecurityResolver.derive_threat_seq(abuse_id)
    assert err is None, f"unexpected error: {err}"
    assert seq == expected_seq


@pytest.mark.parametrize(
    "bad_id",
    [None, "", "   ", "threat-001", "THREAT", "1-001", "THREAT_001", "THREAT-001-extra"],
)
def test_derive_threat_seq_rejects_malformed(bad_id):
    """Missing or malformed ids are rejected with a clear error."""
    seq, err = SecurityResolver.derive_threat_seq(bad_id)
    assert seq is None
    assert err is not None
    assert err  # message present


def test_derive_threat_seq_rejects_tail_above_999():
    seq, err = SecurityResolver.derive_threat_seq("THREAT-1000")
    assert seq is None
    assert "999" in err


# ---------------------------------------------------------------------------
# find_declarations
# ---------------------------------------------------------------------------


_ABUSE_BLOCK_TWO = (
    '- id: "THREAT-001"\n'
    '  name: "Session token leak"\n'
    '  threat: "Attacker exfiltrates session token"\n'
    '  mitigation: "Bind tokens to IP and rotate on privilege change"\n'
    '  severity: "high"\n'
    '  acceptance_ref: "acc:auth:E001-HTTP-001"\n'
    '- id: "THREAT-002"\n'
    '  name: "Replay attack"\n'
    '  threat: "Attacker replays captured session"\n'
    '  mitigation: "Nonce + timestamp validation"\n'
    '  severity: "medium"\n'
    '  acceptance_ref: "acc:auth:E001-HTTP-002"\n'
)


def test_find_declarations_returns_one_per_abuse_case(tmp_path):
    plan = tmp_path / "plan"
    feature_file = _write_feature(
        plan,
        wagon_slug="auth",
        feature_slug="session-management",
        abuse_cases_yaml=_ABUSE_BLOCK_TWO,
    )

    resolver = SecurityResolver(repo_root=tmp_path)
    decls = resolver.find_declarations()

    urns = sorted(d.urn for d in decls)
    assert urns == [
        "security:auth:session-management:001",
        "security:auth:session-management:002",
    ]
    for d in decls:
        assert d.family == "security"
        assert d.context == "abuse_case"
        assert d.source_path == feature_file


def test_find_declarations_metadata_is_verbatim(tmp_path):
    """
    URNDeclaration.metadata exposes id, name, threat, mitigation, severity,
    acceptance_ref string-equal to the YAML source.
    """
    plan = tmp_path / "plan"
    _write_feature(
        plan,
        wagon_slug="auth",
        feature_slug="session-management",
        abuse_cases_yaml=_ABUSE_BLOCK_TWO,
    )

    resolver = SecurityResolver(repo_root=tmp_path)
    decls = {d.urn: d for d in resolver.find_declarations()}
    one = decls["security:auth:session-management:001"]
    assert one.metadata["id"] == "THREAT-001"
    assert one.metadata["name"] == "Session token leak"
    assert one.metadata["threat"] == "Attacker exfiltrates session token"
    assert one.metadata["mitigation"] == "Bind tokens to IP and rotate on privilege change"
    assert one.metadata["severity"] == "high"
    assert one.metadata["acceptance_ref"] == "acc:auth:E001-HTTP-001"


def test_find_declarations_raises_on_malformed_id(tmp_path):
    plan = tmp_path / "plan"
    _write_feature(
        plan,
        wagon_slug="auth",
        feature_slug="bad-feature",
        abuse_cases_yaml=(
            '- id: "lowercase-bad"\n'
            '  name: "Bad id"\n'
            '  threat: "x"\n'
            '  mitigation: "y"\n'
            '  severity: "low"\n'
            '  acceptance_ref: "acc:auth:E001-HTTP-001"\n'
        ),
    )
    resolver = SecurityResolver(repo_root=tmp_path)
    with pytest.raises(ValueError) as excinfo:
        resolver.find_declarations()
    assert "lowercase-bad" in str(excinfo.value)


def test_find_declarations_raises_on_missing_id(tmp_path):
    plan = tmp_path / "plan"
    _write_feature(
        plan,
        wagon_slug="auth",
        feature_slug="missing-id",
        abuse_cases_yaml=(
            '- name: "No id"\n'
            '  threat: "x"\n'
            '  mitigation: "y"\n'
            '  severity: "low"\n'
            '  acceptance_ref: "acc:auth:E001-HTTP-001"\n'
        ),
    )
    resolver = SecurityResolver(repo_root=tmp_path)
    with pytest.raises(ValueError) as excinfo:
        resolver.find_declarations()
    assert "missing required 'id'" in str(excinfo.value)


# ---------------------------------------------------------------------------
# resolve()
# ---------------------------------------------------------------------------


def test_resolve_returns_metadata_with_feature_path(tmp_path):
    plan = tmp_path / "plan"
    feature_file = _write_feature(
        plan,
        wagon_slug="auth",
        feature_slug="session-management",
        abuse_cases_yaml=_ABUSE_BLOCK_TWO,
    )
    resolver = SecurityResolver(repo_root=tmp_path)
    res = resolver.resolve("security:auth:session-management:001")
    assert res.is_resolved
    assert res.is_deterministic
    assert res.resolved_paths == [feature_file]
    assert res.metadata["id"] == "THREAT-001"
    assert res.metadata["acceptance_ref"] == "acc:auth:E001-HTTP-001"


def test_resolve_unknown_seq_is_broken(tmp_path):
    plan = tmp_path / "plan"
    _write_feature(
        plan,
        wagon_slug="auth",
        feature_slug="session-management",
        abuse_cases_yaml=_ABUSE_BLOCK_TWO,
    )
    resolver = SecurityResolver(repo_root=tmp_path)
    res = resolver.resolve("security:auth:session-management:999")
    assert res.is_broken
    assert res.error and "999" in res.error


def test_resolve_invalid_format_returns_error(tmp_path):
    resolver = SecurityResolver(repo_root=tmp_path)
    res = resolver.resolve("security:auth:session-management:abc")
    assert res.is_broken
    assert res.error


# ---------------------------------------------------------------------------
# Registry integration
# ---------------------------------------------------------------------------


def test_registry_finds_security_declarations_across_two_features(tmp_path):
    """
    find_all_declarations(['security']) on plan/ with 2 features × 3
    abuse_cases each returns six URNDeclaration entries with correct
    source_path attribution.
    """
    plan = tmp_path / "plan"
    abuse_three_a = (
        '- id: "THREAT-1"\n'
        '  name: "A1"\n'
        '  threat: "tA1"\n'
        '  mitigation: "mA1"\n'
        '  severity: "low"\n'
        '  acceptance_ref: "acc:auth:E001-HTTP-001"\n'
        '- id: "THREAT-2"\n'
        '  name: "A2"\n'
        '  threat: "tA2"\n'
        '  mitigation: "mA2"\n'
        '  severity: "medium"\n'
        '  acceptance_ref: "acc:auth:E001-HTTP-002"\n'
        '- id: "THREAT-3"\n'
        '  name: "A3"\n'
        '  threat: "tA3"\n'
        '  mitigation: "mA3"\n'
        '  severity: "high"\n'
        '  acceptance_ref: "acc:auth:E001-HTTP-003"\n'
    )
    abuse_three_b = (
        '- id: "ABUSE-10"\n'
        '  name: "B1"\n'
        '  threat: "tB1"\n'
        '  mitigation: "mB1"\n'
        '  severity: "low"\n'
        '  acceptance_ref: "acc:billing:E001-HTTP-001"\n'
        '- id: "ABUSE-11"\n'
        '  name: "B2"\n'
        '  threat: "tB2"\n'
        '  mitigation: "mB2"\n'
        '  severity: "medium"\n'
        '  acceptance_ref: "acc:billing:E001-HTTP-002"\n'
        '- id: "ABUSE-12"\n'
        '  name: "B3"\n'
        '  threat: "tB3"\n'
        '  mitigation: "mB3"\n'
        '  severity: "high"\n'
        '  acceptance_ref: "acc:billing:E001-HTTP-003"\n'
    )
    file_a = _write_feature(plan, "auth", "session-management", abuse_three_a)
    file_b = _write_feature(plan, "billing", "charge-card", abuse_three_b)

    registry = ResolverRegistry(repo_root=tmp_path)
    decls_by_family = registry.find_all_declarations(["security"])
    decls = decls_by_family["security"]
    assert len(decls) == 6
    sources = {d.source_path for d in decls}
    assert sources == {file_a, file_b}
    urns = sorted(d.urn for d in decls)
    assert urns == [
        "security:auth:session-management:001",
        "security:auth:session-management:002",
        "security:auth:session-management:003",
        "security:billing:charge-card:010",
        "security:billing:charge-card:011",
        "security:billing:charge-card:012",
    ]


def test_registry_resolves_security_urn(tmp_path):
    plan = tmp_path / "plan"
    _write_feature(
        plan,
        wagon_slug="auth",
        feature_slug="session-management",
        abuse_cases_yaml=_ABUSE_BLOCK_TWO,
    )
    registry = ResolverRegistry(repo_root=tmp_path)
    res = registry.resolve("security:auth:session-management:002")
    assert res.is_resolved
    assert res.metadata["id"] == "THREAT-002"
