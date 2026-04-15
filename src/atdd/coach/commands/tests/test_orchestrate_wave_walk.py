"""
RED tests for #280 D004 — atdd issue <N> --orchestrate walks the dep graph.

WMBT: wmbt:govern-lifecycle:D004 — acc:govern-lifecycle:D004-UNIT-001-orchestrate-from-single-issue

Covers the two pure helpers that D004 needs:
- _parse_dependencies(body): extract #NNN refs from the ### Dependencies section
- _compute_wave(start, fetch, is_complete): recursive dep walk with cycle
  detection and COMPLETE exclusion.

Run: PYTHONPATH=src python3 -m pytest -q src/atdd/coach/commands/tests/test_orchestrate_wave_walk.py -v
"""
import pytest

pytestmark = [pytest.mark.platform]


def test_d004_parse_dependencies_extracts_hash_refs():
    from atdd.coach.commands.orchestrate_wave_walk import _parse_dependencies

    body = """\
## Scope

### In Scope

- thing

### Dependencies

- #270: frontend invariants
- #282 — transition side effects fix
- (none beyond the two above)

---

## Context

Some ref to #999 in prose — not a dependency.
"""
    deps = _parse_dependencies(body)
    assert deps == [270, 282]


def test_d004_parse_dependencies_handles_empty_section():
    from atdd.coach.commands.orchestrate_wave_walk import _parse_dependencies

    body = """\
### Dependencies

- None.
"""
    assert _parse_dependencies(body) == []


def test_d004_parse_dependencies_returns_empty_when_heading_missing():
    from atdd.coach.commands.orchestrate_wave_walk import _parse_dependencies

    body = "## Scope\n\njust scope, no deps section\n"
    assert _parse_dependencies(body) == []


def test_d004_compute_wave_walks_transitive_deps():
    """The walker returns the full transitive closure starting at `start`."""
    from atdd.coach.commands.orchestrate_wave_walk import _compute_wave

    bodies = {
        100: "### Dependencies\n- #101\n- #102\n",
        101: "### Dependencies\n- #103\n",
        102: "### Dependencies\n- None\n",
        103: "### Dependencies\n- None\n",
    }
    fetch = lambda n: bodies.get(n, "")
    is_complete = lambda n: False

    wave = _compute_wave(100, fetch, is_complete)
    assert set(wave) == {100, 101, 102, 103}
    assert wave[0] == 100


def test_d004_compute_wave_excludes_complete_issues():
    """COMPLETE issues must not appear in the wave, even if referenced."""
    from atdd.coach.commands.orchestrate_wave_walk import _compute_wave

    bodies = {
        100: "### Dependencies\n- #101\n- #102\n",
        101: "### Dependencies\n- None\n",
        102: "### Dependencies\n- None\n",
    }
    fetch = lambda n: bodies.get(n, "")
    completed = {102}
    is_complete = lambda n: n in completed

    wave = _compute_wave(100, fetch, is_complete)
    assert 102 not in wave
    assert 100 in wave
    assert 101 in wave


def test_d004_compute_wave_detects_cycle_without_crashing():
    """A cycle in the dep graph is handled gracefully; every reachable issue
    appears in the wave exactly once.
    """
    from atdd.coach.commands.orchestrate_wave_walk import _compute_wave

    bodies = {
        100: "### Dependencies\n- #101\n",
        101: "### Dependencies\n- #100\n",
    }
    fetch = lambda n: bodies.get(n, "")
    is_complete = lambda n: False

    wave = _compute_wave(100, fetch, is_complete)
    assert sorted(wave) == [100, 101]
