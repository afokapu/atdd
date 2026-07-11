# Component: component:atdd-plan-core:subjects:SubjectInvariants:backend:tests
# Purpose: subject:<name> is a durable-noun URN family with a registry and coherence invariants (#1421).
"""Validators for ``planner.subject.invariants`` (#1421).

``subject:<name>`` is the new 1-token root URN family that gives a typed
``train:<subject>:<slug>`` a real parent (else every train orphans). A subject
is the *durable noun object* of a train's change (``artifact-identity``,
``self-compliance``, ``substrate``) — not a verb, an actor, a theme, a wagon, a
route, a category, an owner, or a program name.

These tests pin the four invariants the ``subject-invariants`` validator enforces
over ``plan/_subjects.yaml`` and the typed trains that reference it:

* **durable noun** — the subject is a noun, not verb-led (inverse of the
  wagon/feature verb-object rule) and not a reserved structural token,
* **registered** — every subject a typed train names is in the registry,
* **unique-by-subject+slug** — no two typed trains collapse to the same identity,
* **registered-before-first-train** — a subject exists in the registry before any
  train is typed under it.

Legacy ``NNNN-slug`` trains (pre-migration) are out of scope for the
per-train invariants — their retyping is the migration tool's job (#1421 Layer 7).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.rule_binding import bind_rule
from atdd.planner import subjects as subj

_REPO_ROOT = Path(__file__).resolve().parents[4]

# Durable nouns — the subjects this migration actually registers.
GOOD_SUBJECTS = [
    "artifact-identity",
    "self-compliance",
    "issue-lifecycle",
    "substrate",
    "object-conflict-resolution",
]

# Each violates exactly one invariant clause.
BAD_SUBJECTS = {
    "resolve-conflicts": "verb-led (resolve is a verb, not a noun object)",
    "commons": "a theme, not a subject",
    "player": "a theme, not a subject",
    "user": "an actor, not a subject",
    "system": "an actor, not a subject",
    "route": "a structural keyword",
    "category": "a structural keyword",
    "owner": "a structural keyword",
    "Artifact-Identity": "not kebab-case",
}


def test_rule_is_bound() -> None:
    rule = bind_rule("planner.subject.invariants")
    assert rule.rule_id == "planner.subject.invariants"


@pytest.mark.parametrize("name", GOOD_SUBJECTS)
def test_durable_nouns_accepted(name: str) -> None:
    ok, reason = subj.is_durable_noun(name)
    assert ok, f"{name!r} should be a durable noun but failed: {reason}"


@pytest.mark.parametrize("name", sorted(BAD_SUBJECTS))
def test_non_nouns_rejected(name: str) -> None:
    ok, reason = subj.is_durable_noun(name)
    assert not ok, f"{name!r} should be rejected ({BAD_SUBJECTS[name]}) but passed"
    assert reason, "a violation must carry a human-readable reason"


def test_repo_subject_registry_satisfies_invariants() -> None:
    """The shipped ``plan/_subjects.yaml`` has no invariant violations."""
    violations = subj.subject_registry_violations(_REPO_ROOT)
    assert violations == [], "registry violations:\n  " + "\n  ".join(violations)


def test_artifact_identity_is_registered() -> None:
    registered = subj.registered_subjects(_REPO_ROOT)
    assert "artifact-identity" in registered


def test_registry_entries_are_unique_by_subject(tmp_path: Path) -> None:
    reg = tmp_path / "plan"
    reg.mkdir()
    (reg / "_subjects.yaml").write_text(
        "version: '1.0'\n"
        "subjects:\n"
        "  - {subject: substrate, title: A, description: d, status: active}\n"
        "  - {subject: substrate, title: B, description: d, status: active}\n",
        encoding="utf-8",
    )
    violations = subj.subject_registry_violations(tmp_path)
    assert any("unique" in v.lower() or "duplicate" in v.lower() for v in violations)


def test_typed_train_must_reference_registered_subject(tmp_path: Path) -> None:
    """A typed ``train:<subject>:<slug>`` whose subject is unregistered is flagged
    (registered-before-first-train)."""
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_subjects.yaml").write_text(
        "version: '1.0'\nsubjects:\n"
        "  - {subject: substrate, title: S, description: d, status: active}\n",
        encoding="utf-8",
    )
    # Typed train under an UNREGISTERED subject.
    (plan / "_trains" / "author-artifacts.yaml").write_text(
        "urn: 'train:ghost-subject:author-artifacts'\n"
        "subject: ghost-subject\n"
        "slug: author-artifacts\n"
        "title: T\n",
        encoding="utf-8",
    )
    violations = subj.unregistered_train_subject_violations(tmp_path)
    assert any("ghost-subject" in v for v in violations)


def test_typed_trains_unique_by_subject_slug(tmp_path: Path) -> None:
    plan = tmp_path / "plan"
    (plan / "_trains").mkdir(parents=True)
    (plan / "_subjects.yaml").write_text(
        "version: '1.0'\nsubjects:\n"
        "  - {subject: substrate, title: S, description: d, status: active}\n",
        encoding="utf-8",
    )
    for i in (1, 2):
        (plan / "_trains" / f"dup{i}.yaml").write_text(
            "urn: 'train:substrate:author-artifacts'\n"
            "subject: substrate\nslug: author-artifacts\ntitle: T\n",
            encoding="utf-8",
        )
    violations = subj.typed_train_uniqueness_violations(tmp_path)
    assert any("author-artifacts" in v for v in violations)
