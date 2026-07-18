"""
Unit tests for the config-driven implementation-root resolvers.

URN: urn:atdd:test:coach:utils:code_root_resolution

Covers `coach.graph.implementation-root-resolution`: roots are declared in
`.atdd/config.yaml`, resolvers take the root as an argument, and unknown stack
keys are skipped rather than crashing (Decision #2 of the code-roots
convention, issue #327; enforced strictly from issue #1476).

The two resolvers answer different questions and must not be conflated:
`resolve_code_root` answers "where is this stack's source?" (web -> web/src),
`resolve_stack_container` answers "where is this stack's project?" (web -> web,
because tsconfig.json is a sibling of src/, not a child).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.utils.config import (
    resolve_code_root,
    resolve_stack_container,
)


pytestmark = [pytest.mark.coach]


REPO = Path("/repo")


def test_defaults_resolve_when_config_declares_nothing():
    """The built-in stack defaults apply to a config with no `code:` block."""
    assert resolve_code_root("python", REPO, config={}) == REPO / "python"
    assert resolve_code_root("web", REPO, config={}) == REPO / "web/src"
    assert (
        resolve_code_root("supabase", REPO, config={}) == REPO / "supabase/functions"
    )


def test_declared_root_overrides_the_default():
    """A consumer that puts its frontend elsewhere is honoured, not overruled."""
    config = {"code": {"web": "apps/frontend/src"}}
    assert resolve_code_root("web", REPO, config=config) == REPO / "apps/frontend/src"


def test_unknown_stack_is_skipped_not_crashed():
    """Decision #2: an undeclared stack resolves to None so callers can skip it.

    This is the property that lets a consumer with no web tier run the web
    validators without failing them, and lets a consumer name `rust` in config
    long before a rust resolver ships.
    """
    assert resolve_code_root("rust", REPO, config={}) is None
    assert resolve_stack_container("rust", REPO, config={}) is None


def test_consumer_may_declare_a_stack_that_has_no_default():
    """Naming a future stack in config makes it resolvable without a fork."""
    config = {"code": {"rust": "crates"}}
    assert resolve_code_root("rust", REPO, config=config) == REPO / "crates"


def test_container_is_not_the_code_root():
    """web source is web/src, but web's manifests sit in web/ — a real distinction.

    Deriving the container from the code root (e.g. taking its first segment)
    would silently produce `apps` for a consumer whose web root is
    `apps/frontend/src`, so the container is declared, not inferred.
    """
    assert resolve_code_root("web", REPO, config={}) == REPO / "web/src"
    assert resolve_stack_container("web", REPO, config={}) == REPO / "web"

    assert (
        resolve_code_root("supabase", REPO, config={}) == REPO / "supabase/functions"
    )
    assert resolve_stack_container("supabase", REPO, config={}) == REPO / "supabase"


def test_container_override_is_independent_of_the_code_root():
    config = {
        "code": {"web": "apps/frontend/src"},
        "stack_containers": {"web": "apps/frontend"},
    }
    assert resolve_code_root("web", REPO, config=config) == REPO / "apps/frontend/src"
    assert (
        resolve_stack_container("web", REPO, config=config) == REPO / "apps/frontend"
    )


@pytest.mark.parametrize("malformed", [None, [], "code", {"code": "python"}])
def test_malformed_config_falls_back_to_defaults_without_raising(malformed):
    """A broken config must not take the whole validator suite down with it."""
    assert resolve_code_root("python", REPO, config=malformed) == REPO / "python"
