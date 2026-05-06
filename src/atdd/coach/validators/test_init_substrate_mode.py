"""
Platform tests: `atdd init` substrate-mode extension (issue #415).

Spec: docs/specs/atdd-repo-substrate-spec-v12.md §9.3
URN: test:coach:substrate:init-mode

Acceptance:
- Heuristic: `plan/` exists AND `src/atdd/` does not → consumer-repo mode.
  Otherwise toolkit mode (covers the live toolkit which has both signals).
- `--consumer-repo` forces consumer-repo mode and writes substrate fields.
- `--toolkit` forces toolkit mode and removes substrate fields.
- Mutually exclusive flags: passing both is rejected.
- Mode persistence: bare `atdd init --force` after a `--consumer-repo` run
  stays in consumer-repo mode (reads existing `repo.substrate.mode`).
- Idempotent under `--force`: two consecutive `--consumer-repo --force` runs
  produce no diff in `.atdd/config.yaml`.
- pytest11 entry-point is registered in pyproject.toml so the substrate
  plugin auto-loads in consumer environments (chosen mechanism per #415).
- pyproject.toml is the toolkit's distribution metadata; the plugin is
  ``atdd.tester.substrate.plugin``.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = [pytest.mark.platform]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _seed_consumer_layout(root: Path) -> None:
    """Fixture layout that the heuristic classifies as consumer-repo."""
    (root / "plan").mkdir(parents=True, exist_ok=True)
    # Deliberately no src/atdd/ — heuristic key.


def _seed_toolkit_layout(root: Path) -> None:
    """Fixture layout that the heuristic classifies as toolkit (both signals)."""
    (root / "plan").mkdir(parents=True, exist_ok=True)
    (root / "src" / "atdd").mkdir(parents=True, exist_ok=True)


def _make_initialized(root: Path) -> "Initializer":  # type: ignore[name-defined]
    """Return a fresh Initializer with `.atdd/` already bootstrapped."""
    from atdd.coach.commands.initializer import Initializer

    init = Initializer(target_dir=root)
    init.atdd_config_dir.mkdir(parents=True, exist_ok=True)
    # Minimal valid config so substrate-mode helpers can read/write.
    init._create_config(force=True)
    return init


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_initializer_exposes_substrate_constants():
    """Constants for mode names + plugin entry-point id exist on the module."""
    from atdd.coach.commands import initializer

    for name in (
        "SUBSTRATE_MODE_CONSUMER",
        "SUBSTRATE_MODE_TOOLKIT",
        "SUBSTRATE_PLUGIN_ENTRY_POINT",
    ):
        assert hasattr(initializer, name), f"initializer must expose {name}"

    assert initializer.SUBSTRATE_MODE_CONSUMER == "consumer-repo"
    assert initializer.SUBSTRATE_MODE_TOOLKIT == "toolkit"
    assert initializer.SUBSTRATE_PLUGIN_ENTRY_POINT == "atdd.tester.substrate.plugin"


def test_initializer_exposes_resolution_methods():
    """Resolution + apply methods are part of the Initializer surface."""
    from atdd.coach.commands.initializer import Initializer

    for name in (
        "detect_substrate_mode_heuristic",
        "resolve_substrate_mode",
        "_apply_substrate_mode",
        "_write_substrate_config",
        "_remove_substrate_config",
    ):
        assert hasattr(Initializer, name), f"Initializer must define {name}"


# ---------------------------------------------------------------------------
# Heuristic detection (spec v12 §9.3)
# ---------------------------------------------------------------------------


def test_heuristic_classifies_consumer_when_only_plan_present(tmp_path):
    """plan/ + no src/atdd/ → consumer-repo."""
    from atdd.coach.commands.initializer import Initializer

    _seed_consumer_layout(tmp_path)
    init = Initializer(target_dir=tmp_path)
    assert init.detect_substrate_mode_heuristic() == "consumer-repo"


def test_heuristic_classifies_toolkit_when_both_signals_present(tmp_path):
    """plan/ AND src/atdd/ → toolkit (the live-toolkit case)."""
    from atdd.coach.commands.initializer import Initializer

    _seed_toolkit_layout(tmp_path)
    init = Initializer(target_dir=tmp_path)
    assert init.detect_substrate_mode_heuristic() == "toolkit"


def test_heuristic_classifies_toolkit_when_neither_signal_present(tmp_path):
    """Empty repo (no plan/, no src/atdd/) → toolkit (substrate inactive)."""
    from atdd.coach.commands.initializer import Initializer

    init = Initializer(target_dir=tmp_path)
    assert init.detect_substrate_mode_heuristic() == "toolkit"


# ---------------------------------------------------------------------------
# Override precedence
# ---------------------------------------------------------------------------


def test_consumer_repo_flag_overrides_heuristic(tmp_path):
    """--consumer-repo wins on a layout the heuristic would call toolkit."""
    from atdd.coach.commands.initializer import Initializer

    _seed_toolkit_layout(tmp_path)
    init = Initializer(target_dir=tmp_path)
    assert init.resolve_substrate_mode(force_consumer=True) == "consumer-repo"


def test_toolkit_flag_overrides_heuristic(tmp_path):
    """--toolkit wins on a layout the heuristic would call consumer-repo."""
    from atdd.coach.commands.initializer import Initializer

    _seed_consumer_layout(tmp_path)
    init = Initializer(target_dir=tmp_path)
    assert init.resolve_substrate_mode(force_toolkit=True) == "toolkit"


def test_existing_mode_in_config_overrides_heuristic(tmp_path):
    """Bare `atdd init` after a prior `--consumer-repo` stays in mode."""
    init = _make_initialized(tmp_path)
    # Wipe layout signals so the heuristic would say "toolkit"
    if (tmp_path / "plan").is_dir():
        (tmp_path / "plan").rmdir()
    init._write_substrate_config()  # writes mode: consumer-repo

    # Bare invocation: heuristic would say "toolkit", but persisted mode wins.
    assert init.resolve_substrate_mode() == "consumer-repo"


def test_explicit_flag_wins_over_persisted_mode(tmp_path):
    """`--toolkit` after a previous `--consumer-repo` flips back."""
    init = _make_initialized(tmp_path)
    init._write_substrate_config()
    assert init.resolve_substrate_mode(force_toolkit=True) == "toolkit"


def test_init_rejects_both_flags(tmp_path):
    """`atdd init --consumer-repo --toolkit` returns non-zero."""
    from atdd.coach.commands.initializer import Initializer

    init = Initializer(target_dir=tmp_path)
    rc = init.init(force=True, consumer_repo=True, toolkit=True)
    assert rc == 1


# ---------------------------------------------------------------------------
# Config writing / removing
# ---------------------------------------------------------------------------


def _read_config(root: Path) -> dict:
    return yaml.safe_load((root / ".atdd" / "config.yaml").read_text()) or {}


def test_consumer_mode_writes_substrate_block(tmp_path):
    """`_write_substrate_config` populates repo.test_root/plan_root/substrate."""
    init = _make_initialized(tmp_path)
    init._write_substrate_config()

    cfg = _read_config(tmp_path)
    assert cfg["repo"]["test_root"] == "tests/"
    assert cfg["repo"]["plan_root"] == "plan/"
    assert cfg["repo"]["substrate"]["enabled"] is True
    assert cfg["repo"]["substrate"]["plugin"] == "atdd.tester.substrate.plugin"
    assert cfg["repo"]["substrate"]["mode"] == "consumer-repo"


def test_toolkit_mode_removes_substrate_block(tmp_path):
    """`_remove_substrate_config` strips the `repo:` block when present."""
    init = _make_initialized(tmp_path)
    init._write_substrate_config()
    assert "repo" in _read_config(tmp_path)

    init._remove_substrate_config()
    cfg = _read_config(tmp_path)
    assert "repo" not in cfg


def test_remove_is_no_op_when_no_repo_block(tmp_path):
    """`_remove_substrate_config` on a fresh config is a no-op."""
    init = _make_initialized(tmp_path)
    before = (tmp_path / ".atdd" / "config.yaml").read_text()
    init._remove_substrate_config()
    after = (tmp_path / ".atdd" / "config.yaml").read_text()
    assert before == after


def test_consumer_force_init_idempotent(tmp_path):
    """Two `init --consumer-repo --force` runs produce no diff on the second."""
    from atdd.coach.commands.initializer import Initializer

    _seed_consumer_layout(tmp_path)

    # First run.
    Initializer(target_dir=tmp_path).init(
        force=True, consumer_repo=True,
    )
    first = (tmp_path / ".atdd" / "config.yaml").read_text()

    # Second run.
    Initializer(target_dir=tmp_path).init(
        force=True, consumer_repo=True,
    )
    second = (tmp_path / ".atdd" / "config.yaml").read_text()

    # toolkit.last_version is rewritten on every run with the current version,
    # so a strict byte-for-byte equality could regress on a version bump in
    # the same call. The substrate fields under repo: must be identical.
    cfg_first = yaml.safe_load(first)
    cfg_second = yaml.safe_load(second)
    assert cfg_first.get("repo") == cfg_second.get("repo")
    # And second equals first overall (the version is fixed during one run).
    assert first == second


def test_consumer_then_toolkit_force_init_removes_substrate(tmp_path):
    """`init --consumer-repo --force` then `init --toolkit --force` cleans up."""
    from atdd.coach.commands.initializer import Initializer

    _seed_consumer_layout(tmp_path)

    Initializer(target_dir=tmp_path).init(
        force=True, consumer_repo=True,
    )
    assert "repo" in _read_config(tmp_path)

    Initializer(target_dir=tmp_path).init(
        force=True, toolkit=True,
    )
    assert "repo" not in _read_config(tmp_path)


# ---------------------------------------------------------------------------
# pytest11 entry-point registration
# ---------------------------------------------------------------------------


def test_pyproject_registers_pytest11_entry_point():
    """`pyproject.toml` must declare the substrate plugin under pytest11."""
    try:
        import tomllib
    except ImportError:  # Python < 3.11
        import tomli as tomllib  # type: ignore[import-not-found]

    # Walk up from this test file to the toolkit pyproject.toml.
    pyproject = Path(__file__).resolve()
    for ancestor in pyproject.parents:
        candidate = ancestor / "pyproject.toml"
        if candidate.is_file():
            pyproject = candidate
            break
    else:
        pytest.skip("pyproject.toml not found in any ancestor of this test")

    with open(pyproject, "rb") as fh:
        data = tomllib.load(fh)

    pytest11 = (
        data.get("project", {})
        .get("entry-points", {})
        .get("pytest11", {})
    )
    assert pytest11, (
        "pyproject.toml must declare a [project.entry-points.pytest11] block "
        "registering the substrate plugin per spec v12 §9.3."
    )
    # The substrate plugin is the entry-point we care about; allow any name.
    assert "atdd.tester.substrate.plugin" in pytest11.values(), (
        "pytest11 entry-point must point at atdd.tester.substrate.plugin, "
        f"got: {pytest11!r}"
    )


# ---------------------------------------------------------------------------
# Substrate plugin runtime gate
# ---------------------------------------------------------------------------


def test_substrate_plugin_disabled_in_toolkit_mode(tmp_path):
    """`_substrate_enabled` returns False when no `repo:` block is present."""
    from atdd.tester.substrate.plugin import _substrate_enabled

    (tmp_path / ".atdd").mkdir()
    (tmp_path / ".atdd" / "config.yaml").write_text(
        "version: '1.0'\nrelease:\n  version_file: pyproject.toml\n"
    )
    assert _substrate_enabled(tmp_path) is False


def test_substrate_plugin_enabled_after_consumer_init(tmp_path):
    """After consumer-repo init, the runtime gate returns True."""
    from atdd.tester.substrate.plugin import _substrate_enabled

    init = _make_initialized(tmp_path)
    init._write_substrate_config()

    assert _substrate_enabled(tmp_path) is True
