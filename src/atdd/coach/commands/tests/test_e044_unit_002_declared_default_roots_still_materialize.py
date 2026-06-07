# URN: test:govern-lifecycle:registry-build-honors-declared-code-roots:E044-UNIT-002-declared-default-roots-still-materialize
# Acceptance: acc:govern-lifecycle:E044-UNIT-002-declared-default-roots-still-materialize
# WMBT: wmbt:govern-lifecycle:E044
# Phase: GREEN
"""acc:govern-lifecycle:E044-UNIT-002 — the game-template default roots stay
available: a repo that explicitly declares ``python`` and ``supabase`` in its
``.atdd/config.yaml`` ``code:`` block still gets their mirrors materialized.

This guards against over-gating: the fix removes the FORCING of
DEFAULT_CODE_ROOTS, not the defaults themselves. A repo that opts in must keep
its python/_implementations.yaml and supabase/_functions.yaml mirrors (#984).
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path

import yaml

from atdd.coach.commands.registry import RegistryBuilder


def _make_repo(root: Path, code_block: dict) -> Path:
    (root / ".atdd").mkdir(parents=True, exist_ok=True)
    (root / ".atdd" / "config.yaml").write_text(
        yaml.safe_dump({"version": "1.0", "code": code_block}, sort_keys=False),
        encoding="utf-8",
    )
    return root


def test_declared_default_roots_still_materialize(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"python": "python", "supabase": "supabase/functions"})
    builder = RegistryBuilder(repo)

    with contextlib.redirect_stdout(io.StringIO()):
        builder.build_all(mode="apply")

    assert (repo / "python" / "_implementations.yaml").exists(), (
        "a repo that declares code.python must still get its python mirror"
    )
    assert (repo / "supabase" / "_functions.yaml").exists(), (
        "a repo that declares code.supabase must still get its supabase mirror"
    )
