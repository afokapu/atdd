# URN: test:consolidate-coach-workspace:enforce-surface-conformance:E004-UNIT-001-build-sanitize-parse-roundtrip
# Acceptance: acc:consolidate-coach-workspace:E004-UNIT-001-build-sanitize-parse-roundtrip
# WMBT: wmbt:consolidate-coach-workspace:E004
# Phase: RED
# Layer: domain
# Assertion: behavioral
"""E004-UNIT-001 — role-aware canonical naming: builder + sanitizer + parser.

`<REPO><N>[-phaseN]-<role>-<slug>`, role in {worker, coach-daemon, observer}.
Reuses the #470 primitive for the base shape; an unknown role never parses and an
invalid role never builds."""
from __future__ import annotations

import pytest

from atdd.consolidate_coach_workspace.enforce_surface_conformance.src.domain.canonical_name import (
    ParsedRoleName,
    build_role_aware_name,
    is_role_aware_name,
    parse_role_aware_name,
    sanitize_slug,
)


def test_builder_produces_role_aware_shape():
    assert (
        build_role_aware_name("ATDD", 865, "worker", "Coach Layout!!")
        == "ATDD865-worker-coach-layout"
    )


def test_builder_carries_phase_infix():
    assert (
        build_role_aware_name("ATDD", 462, "coach-daemon", "bump-on-merge", phase=2)
        == "ATDD462-phase2-coach-daemon-bump-on-merge"
    )


def test_sanitizer_lowercases_strips_and_truncates():
    out = sanitize_slug("Some  Weird__Slug!!")
    assert out == "some-weird-slug"
    long = sanitize_slug("a" * 60)
    assert len(long) <= 40


def test_parser_roundtrips_including_role():
    parsed = parse_role_aware_name("ATDD865-worker-coach-layout")
    assert parsed == ParsedRoleName(
        repo="ATDD", issue=865, phase=None, role="worker", slug="coach-layout"
    )


def test_unknown_role_does_not_parse():
    assert parse_role_aware_name("ATDD865-wizard-foo") is None
    assert is_role_aware_name("ATDD865-wizard-foo") is False


def test_legacy_name_without_role_is_not_role_aware():
    # The #470 shape (no role segment) is NOT role-aware.
    assert is_role_aware_name("ATDD865-coach-layout") is False


def test_invalid_role_raises_on_build():
    with pytest.raises(ValueError):
        build_role_aware_name("ATDD", 865, "wizard", "foo")
