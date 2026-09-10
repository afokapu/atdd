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

# Each violates exactly one invariant clause. These are the clauses that hold
# in EVERY repo — shape, actor and structural keyword. The "not a theme" clause
# is deliberately absent: no theme name is universally reserved (a consumer's
# `themes:` block can rename any digit, digit 0 included, and `get_theme_map`
# honours it), so naming one here would assert the toolkit's own vocabulary
# rather than the rule. It is covered hermetically below.
BAD_SUBJECTS = {
    "resolve-conflicts": "verb-led (resolve is a verb, not a noun object)",
    "user": "an actor, not a subject",
    "system": "an actor, not a subject",
    "route": "a structural keyword",
    "category": "a structural keyword",
    "owner": "a structural keyword",
    "Artifact-Identity": "not kebab-case",
}

#: A repo whose themes are these — chosen to overlap nothing in GOOD_SUBJECTS
#: and nothing in DEFAULT_THEME_MAP, so the assertions below cannot be
#: satisfied by an ambient vocabulary leaking in from anywhere else.
_LAB_THEMES = {"1": "cartography", "5": "husbandry"}


@pytest.fixture()
def themed_repo(tmp_path: Path) -> Path:
    """A repo root whose `.atdd/config.yaml` declares `_LAB_THEMES`."""
    cfg = tmp_path / ".atdd"
    cfg.mkdir()
    body = "\n".join(f"  '{d}': {name}" for d, name in sorted(_LAB_THEMES.items()))
    (cfg / "config.yaml").write_text(f"version: '1.0'\nthemes:\n{body}\n", encoding="utf-8")
    return tmp_path


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


# --- the "a theme is not a subject" clause -------------------------------
# Asserted against a vocabulary the test supplies, never against the toolkit's
# own defaults: `is_durable_noun` resolves themes per-repo, so hardcoding a
# name here would fail in any consumer that renamed that digit.


@pytest.mark.parametrize("theme", sorted(_LAB_THEMES.values()))
def test_a_theme_of_the_repo_is_not_a_subject(themed_repo: Path, theme: str) -> None:
    ok, reason = subj.is_durable_noun(theme, root=themed_repo)
    assert not ok, f"{theme!r} is a theme of this repo and must be rejected as a subject"
    assert "theme" in (reason or ""), f"reason must name the theme clause, got: {reason}"


def test_a_theme_of_another_repo_is_still_a_subject(themed_repo: Path) -> None:
    """The clause reserves THIS repo's themes, not the toolkit's built-ins.

    `player` is digit 5 in `DEFAULT_THEME_MAP` but not a theme of `themed_repo`,
    so it is an ordinary durable noun there. This is the assertion that fails if
    the theme set is ever resolved from anywhere but the given root.
    """
    ok, reason = subj.is_durable_noun("player", root=themed_repo)
    assert ok, f"'player' is not a theme of this repo and must be accepted: {reason}"


def test_theme_clause_needs_a_root() -> None:
    """With no root there is no repo and no theme vocabulary — the structural
    blocklist alone applies, and the answer does not depend on the process's
    working directory."""
    for name in ("player", "commons", "cartography"):
        ok, _ = subj.is_durable_noun(name)
        assert ok, f"{name!r} is not structurally reserved; rootless call must accept it"
    ok, _ = subj.is_durable_noun("route")
    assert not ok, "the structural blocklist still applies with no root"


def test_theme_clause_ignores_the_working_directory(themed_repo: Path, monkeypatch) -> None:
    """The regression pin for the defect itself.

    `_reserved_themes` used to fall back to `Path(".")` when given no root, so
    the rootless call silently answered out of whatever `.atdd/config.yaml`
    happened to sit in the process's cwd. That made this shipped validator a
    function of the CONSUMER's theme block: `player` is digit 5 by default, so
    a consumer that renamed digit 5 saw `is_durable_noun("player")` flip to True
    and every `git push` from that repo fail on a test about the toolkit's
    vocabulary. Same call, same argument, different answer per directory.
    """
    outside = subj.is_durable_noun("husbandry")
    monkeypatch.chdir(themed_repo)
    inside = subj.is_durable_noun("husbandry")
    assert inside == outside, (
        "is_durable_noun() with no root must not read the cwd's .atdd/config.yaml; "
        f"got {outside} outside the themed repo and {inside} inside it"
    )


@pytest.mark.platform  # toolkit dogfood: reads toolkit-only repo state (#1475)
def test_repo_subject_registry_satisfies_invariants() -> None:
    """The shipped ``plan/_subjects.yaml`` has no invariant violations."""
    violations = subj.subject_registry_violations(_REPO_ROOT)
    assert violations == [], "registry violations:\n  " + "\n  ".join(violations)


@pytest.mark.platform  # toolkit dogfood: reads toolkit-only repo state (#1475)
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
