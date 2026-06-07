# URN: test:govern-lifecycle:registry-build-honors-declared-code-roots:E044-SMOKE-001-toolkit-registry-build-leaves-no-stray-stub-dirs
# Acceptance: acc:govern-lifecycle:E044-SMOKE-001-toolkit-registry-build-leaves-no-stray-stub-dirs
# WMBT: wmbt:govern-lifecycle:E044
# Phase: SMOKE
"""acc:govern-lifecycle:E044-SMOKE-001 — LIVE smoke against the toolkit's own
shipped artifact: the real ``.atdd/config.yaml`` that this repo commits, run
through the real production ``RegistryBuilder.build_all``, leaves NO stray
python/, supabase/ or telemetry/ stub dirs.

No fakes, no mocks, no synthetic fixtures (see the #855 fake-green history): the
test reads the committed ``.atdd/config.yaml`` (the artifact the fix changed) and
drives the same ``build_all(mode="apply")`` that ``atdd registry update --apply``
and ``atdd pr`` run. The build executes against a temp checkout seeded with the
LIVE config so the toolkit worktree is never mutated, but the config and the code
path are both the real shipped ones.
"""
from __future__ import annotations

import contextlib
import io
from pathlib import Path

import pytest
import yaml

from atdd.coach.commands.registry import RegistryBuilder

pytestmark = [pytest.mark.smoke]

# .../feat-*/src/atdd/coach/commands/tests/<file> → parents[5] == worktree root
REPO_ROOT = Path(__file__).resolve().parents[5]


def test_toolkit_registry_build_leaves_no_stray_stub_dirs(tmp_path: Path) -> None:
    live_config_path = REPO_ROOT / ".atdd" / "config.yaml"
    assert live_config_path.exists(), f"missing live config at {live_config_path}"
    live_config_text = live_config_path.read_text(encoding="utf-8")

    # The shipped config must declare only the toolkit code root — the vestigial
    # game-template defaults (python/supabase/web) are gone (#984, sibling #970).
    cfg = yaml.safe_load(live_config_text) or {}
    code = cfg.get("code") or {}
    assert code.get("toolkit") == "src/atdd", (
        "toolkit .atdd/config.yaml must declare code.toolkit: src/atdd"
    )
    for forced in ("python", "supabase", "web"):
        assert forced not in code, (
            f"toolkit .atdd/config.yaml still declares the vestigial "
            f"game-template code root {forced!r} — drop it so the registry build "
            f"does not materialize a {forced}/ stub dir."
        )

    # Drive the REAL production build against a repo seeded with the LIVE config.
    seeded = tmp_path / "repo"
    (seeded / ".atdd").mkdir(parents=True)
    (seeded / ".atdd" / "config.yaml").write_text(live_config_text, encoding="utf-8")

    builder = RegistryBuilder(seeded)
    with contextlib.redirect_stdout(io.StringIO()):
        builder.build_all(mode="apply")

    for stub in ("python", "supabase", "telemetry"):
        assert not (seeded / stub).exists(), (
            f"the toolkit's shipped config still produced a stray {stub}/ stub "
            f"dir after a registry build — the operator must rm -rf it by hand."
        )
