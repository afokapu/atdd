# URN: test:govern-lifecycle:registry-build-honors-declared-code-roots:E044-UNIT-003-declared-code-roots-excludes-merged-defaults
# Acceptance: acc:govern-lifecycle:E044-UNIT-003-declared-code-roots-excludes-merged-defaults
# WMBT: wmbt:govern-lifecycle:E044
# Phase: GREEN
"""acc:govern-lifecycle:E044-UNIT-003 — RegistryBuilder._declared_code_roots()
returns ONLY the keys explicitly declared in the repo's ``.atdd/config.yaml``
``code:`` block, never the merged game-template DEFAULT_CODE_ROOTS that
get_code_roots() folds in.

This is the seam that lets build_all distinguish "the repo ships python" from
"python is a built-in default" — the distinction the stub-dir bug erased (#984).
"""
from __future__ import annotations

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


def test_declared_code_roots_excludes_merged_defaults(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, {"toolkit": "src/atdd"})
    builder = RegistryBuilder(repo)

    declared = builder._declared_code_roots()

    assert "toolkit" in declared, "explicitly-declared root must be reported"
    assert "python" not in declared, (
        "_declared_code_roots must NOT fold in the DEFAULT_CODE_ROOTS"
    )
    assert "supabase" not in declared, (
        "_declared_code_roots must NOT fold in the DEFAULT_CODE_ROOTS"
    )
    assert "web" not in declared, (
        "_declared_code_roots must NOT fold in the DEFAULT_CODE_ROOTS"
    )
