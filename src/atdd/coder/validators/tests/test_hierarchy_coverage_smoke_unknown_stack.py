"""
SMOKE: the hierarchy-coverage validator must not crash on consumer repos
that declare a stack key (e.g. ``code.rust: crates/``) for which no
resolver has shipped yet.

URN: urn:atdd:test:coder:hierarchy_coverage_smoke_unknown_stack
WMBT: wmbt:govern-lifecycle:D011 (multi-stack adoption)

This is Phase 3 / SMOKE Fixture B from #327. Decision #2: the validator
iterates only over keys with known resolvers and skips unknown ones with
a DEBUG log. Forward-compatible — consumers can declare future stacks in
config before resolvers exist; no validator crash.
"""

from __future__ import annotations

import logging
import textwrap
from pathlib import Path

import pytest

from atdd.coach.utils.config import get_code_roots, load_atdd_config
from atdd.coder.validators.test_hierarchy_coverage import (
    _iter_resolvers,
    has_implementation,
)


pytestmark = [pytest.mark.platform]


def _scaffold_consumer_repo(root: Path) -> None:
    """Build the minimum viable ATDD consumer repo layout under ``root``."""
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    (root / "plan" / "sample_wagon" / "features").mkdir(parents=True, exist_ok=True)
    (root / "contracts").mkdir(parents=True, exist_ok=True)
    (root / "crates").mkdir(parents=True, exist_ok=True)
    (root / ".atdd" / "config.yaml").write_text(
        textwrap.dedent(
            """\
            version: '1.0'
            release:
              version_file: Cargo.toml
              tag_prefix: v
            code:
              rust: crates
            """
        ),
        encoding="utf-8",
    )
    (root / ".atdd" / "manifest.yaml").write_text(
        "version: '2.0'\nsessions: []\n", encoding="utf-8"
    )


def test_unknown_stack_key_skipped_not_crashed(tmp_path, caplog):
    """Decision #2: rust key declared; no resolver shipped → skipped silently."""
    _scaffold_consumer_repo(tmp_path)

    config = load_atdd_config(tmp_path)
    code_roots = get_code_roots(config)

    assert "rust" in code_roots
    assert code_roots["rust"] == Path("crates")

    caplog.set_level(logging.DEBUG, logger="atdd.coder.validators.test_hierarchy_coverage")
    resolved_stacks = [stack for stack, _resolver, _root in _iter_resolvers(code_roots)]
    assert "rust" not in resolved_stacks, "rust has no resolver and must be skipped"

    # Standard default stacks still appear even though the consumer only
    # declared 'rust' — defaults always apply (Decision #1 baseline).
    assert {"python", "supabase", "web"}.issubset(set(resolved_stacks))

    # Graceful skip emits a DEBUG log — visible when the root logger is
    # below DEBUG, silent in production.
    messages = [r.getMessage() for r in caplog.records]
    assert any("No resolver for stack" in m and "rust" in m for m in messages), (
        "expected DEBUG log for unknown stack key"
    )


def test_has_implementation_does_not_crash_on_unknown_stack(tmp_path):
    """Even with no registered resolver for 'rust', has_implementation
    returns False (not raises) so the ratchet test stays stable."""
    _scaffold_consumer_repo(tmp_path)
    code_roots = get_code_roots(load_atdd_config(tmp_path))

    result = has_implementation(
        "sample-wagon", "nonexistent-feature", code_roots=code_roots
    )
    assert result is False
