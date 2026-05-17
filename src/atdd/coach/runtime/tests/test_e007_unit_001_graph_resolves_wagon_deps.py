# URN: test:integration-hardening:coach-graph-aware-orchestration:E007-UNIT-001-graph-resolves-wagon-deps
# Acceptance: acc:integration-hardening:E007-UNIT-001-graph-resolves-wagon-deps
# WMBT: wmbt:integration-hardening:E007
# Phase: RED
# Layer: unit
# Runtime: python
"""E007-UNIT-001 — ``coach.runtime.graph.wagon_deps(wagon)`` returns the list
of wagons that the given wagon consumes from.

The helper reads ``plan/<wagon>/_<wagon>.yaml::consume[].from`` and returns the
bare wagon slugs (no ``wagon:`` URN prefix). A wagon with an empty consume list
returns ``[]``.

RED expectation: ``atdd.coach.runtime.graph`` does not exist yet, so the import
inside the test raises ``ModuleNotFoundError`` and the test fails.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytestmark = [pytest.mark.platform]


def _make_wagon(plan_dir: Path, slug: str, consume: list[str]) -> None:
    """Scaffold plan/<slug>/_<slug>.yaml with the given consume edges."""
    wagon_dir = plan_dir / slug.replace("-", "_")
    wagon_dir.mkdir(parents=True)
    consume_block = "consume: []\n"
    if consume:
        lines = "".join(f"  - name: edge\n    from: wagon:{c}\n" for c in consume)
        consume_block = f"consume:\n{lines}"
    (wagon_dir / f"_{slug.replace('-', '_')}.yaml").write_text(
        textwrap.dedent(f"""\
            wagon: {slug}
            urn: "wagon:{slug}"
            name: "Test Wagon {slug}"
            description: "Wagon for E007 unit testing."
            theme: commons
            features: []
            produce: []
        """)
        + consume_block
    )


def test_wagon_deps_returns_consumed_wagon_slugs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_dir = tmp_path / "plan"
    _make_wagon(plan_dir, "wagon-a", consume=[])
    _make_wagon(plan_dir, "wagon-b", consume=["wagon-a"])
    monkeypatch.chdir(tmp_path)

    from atdd.coach.runtime.graph import wagon_deps

    assert wagon_deps("wagon-b") == ["wagon-a"]


def test_wagon_deps_returns_empty_for_independent_wagon(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_dir = tmp_path / "plan"
    _make_wagon(plan_dir, "wagon-a", consume=[])
    _make_wagon(plan_dir, "wagon-b", consume=["wagon-a"])
    monkeypatch.chdir(tmp_path)

    from atdd.coach.runtime.graph import wagon_deps

    deps = wagon_deps("wagon-a")
    assert deps == []
    assert isinstance(deps, list)


def test_wagon_deps_strips_wagon_urn_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    plan_dir = tmp_path / "plan"
    _make_wagon(plan_dir, "wagon-a", consume=[])
    _make_wagon(plan_dir, "wagon-b", consume=["wagon-a"])
    monkeypatch.chdir(tmp_path)

    from atdd.coach.runtime.graph import wagon_deps

    # Bare slug, never the "wagon:" URN form.
    assert all(not d.startswith("wagon:") for d in wagon_deps("wagon-b"))
