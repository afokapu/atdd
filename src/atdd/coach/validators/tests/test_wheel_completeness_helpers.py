# URN: component:govern-lifecycle:enforcement-substrate:test_wheel_completeness_helpers:backend:domain
# Runtime: python
# Purpose: Unit tests for wheel-completeness helper functions (issue #451).

"""
Unit tests for ``test_wheel_completeness`` helper functions.

The integration test ``test_validator_fixtures_present_in_wheel`` is meant
to fire in CI on a wheel-built environment (source tree + installed wheel
both reachable, but distinct). Locally, pytest's
``pyproject.toml::pythonpath = ["src"]`` makes ``atdd`` import from the
source tree, so the integration test legitimately ``pytest.skip``s.

These unit tests use ``tmp_path`` to construct synthetic source-tree and
install-tree layouts, then exercise the helpers directly.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.validators.test_wheel_completeness import (
    _is_cache_cruft,
    build_violations,
    collect_source_fixture_files,
    expected_install_path,
    find_missing_fixtures,
    is_editable_install,
)


pytestmark = [pytest.mark.coach, pytest.mark.platform]


# ---------------------------------------------------------------------------
# _is_cache_cruft — recognizes build-artifacts the wheel must not ship
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "path",
    [
        Path("foo/__pycache__/bar.cpython-314.pyc"),
        Path("foo/.pytest_cache/v/lastfailed"),
        Path("foo/bar.pyc"),
        Path("foo/bar.pyo"),
        Path("foo/.DS_Store"),
        Path("foo/__pycache__/whatever"),
    ],
)
def test_cache_cruft_recognized(path: Path):
    assert _is_cache_cruft(path) is True


@pytest.mark.parametrize(
    "path",
    [
        Path("foo/harness_output.json"),
        Path("foo/bar/test_minimal_pass.py"),
        Path("foo/bar/__init__.py"),
        Path("foo/baz/data.yaml"),
    ],
)
def test_legitimate_files_not_cache_cruft(path: Path):
    assert _is_cache_cruft(path) is False


# ---------------------------------------------------------------------------
# Synthetic source-tree fixture builder
# ---------------------------------------------------------------------------
def _build_synthetic_src_atdd(root: Path) -> Path:
    """Construct a minimal ``<root>/src/atdd/...`` tree mirroring the real
    multi-phase fixture layout. Returns the ``src/atdd`` path.
    """
    src_atdd = root / "src" / "atdd"
    # Toolkit's pyproject marker for find_repo_src_atdd discovery.
    (root / "pyproject.toml").write_text("[project]\nname='synthetic-atdd'\n")
    # Three phases with one fixture each + cache-cruft alongside.
    for phase, fixture_rel in (
        ("tester", "train_renders/pass/harness_output.json"),
        ("coach", "minimal_repo/test_minimal_pass.py"),
        ("coder", "silent_swallow/python_clean/observed_handlers.py"),
    ):
        fpath = src_atdd / phase / "validators" / "fixtures" / fixture_rel
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text("# fixture content\n")
        # Sprinkle cache-cruft to confirm the scanner ignores it.
        cache = fpath.parent / "__pycache__" / "stale.cpython-314.pyc"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b"\x00\x00")
        ds = fpath.parent / ".DS_Store"
        ds.write_bytes(b"\x00")
    return src_atdd


# ---------------------------------------------------------------------------
# collect_source_fixture_files — walks every phase's fixture tree, skips cruft
# ---------------------------------------------------------------------------
def test_collect_source_fixture_files_walks_all_phases(tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    files = collect_source_fixture_files(src_atdd)
    rels = sorted(f.relative_to(src_atdd).as_posix() for f in files)
    assert rels == [
        "coach/validators/fixtures/minimal_repo/test_minimal_pass.py",
        "coder/validators/fixtures/silent_swallow/python_clean/"
        "observed_handlers.py",
        "tester/validators/fixtures/train_renders/pass/harness_output.json",
    ]


def test_collect_source_fixture_files_excludes_cache_cruft(tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    files = collect_source_fixture_files(src_atdd)
    for f in files:
        assert "__pycache__" not in f.parts
        assert f.suffix not in (".pyc", ".pyo")
        assert f.name != ".DS_Store"


def test_collect_source_fixture_files_handles_missing_phases(tmp_path: Path):
    """When a phase has no ``validators/fixtures/`` tree, it's skipped silently."""
    src_atdd = tmp_path / "src" / "atdd"
    (src_atdd / "tester" / "validators" / "fixtures").mkdir(parents=True)
    only_file = src_atdd / "tester" / "validators" / "fixtures" / "single.json"
    only_file.write_text("{}")
    # planner exists but has no fixtures dir
    (src_atdd / "planner").mkdir(parents=True)
    files = collect_source_fixture_files(src_atdd)
    assert [f.name for f in files] == ["single.json"]


# ---------------------------------------------------------------------------
# expected_install_path — maps src to install location
# ---------------------------------------------------------------------------
def test_expected_install_path_strips_src_atdd_prefix(tmp_path: Path):
    src_atdd = tmp_path / "src" / "atdd"
    install_dir = tmp_path / "site-packages" / "atdd"
    src_file = (
        src_atdd
        / "tester"
        / "validators"
        / "fixtures"
        / "train_renders"
        / "pass"
        / "harness_output.json"
    )
    expected = expected_install_path(src_file, src_atdd, install_dir)
    assert expected == install_dir / "tester" / "validators" / "fixtures" / (
        "train_renders/pass/harness_output.json"
    ).replace("/", "/")
    assert expected.relative_to(install_dir) == src_file.relative_to(src_atdd)


# ---------------------------------------------------------------------------
# find_missing_fixtures — diffs source tree against install location
# ---------------------------------------------------------------------------
def test_find_missing_fixtures_complete_install(tmp_path: Path):
    """When every source-tree fixture is mirrored under the install dir,
    the scan returns no missing entries.
    """
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    install_dir = tmp_path / "site-packages" / "atdd"
    for src in collect_source_fixture_files(src_atdd):
        target = expected_install_path(src, src_atdd, install_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(src.read_bytes())
    missing = find_missing_fixtures(
        collect_source_fixture_files(src_atdd), src_atdd, install_dir
    )
    assert missing == []


def test_find_missing_fixtures_detects_dropped_files(tmp_path: Path):
    """When the install dir is missing one fixture, that file is flagged
    with the correct expected path.
    """
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    install_dir = tmp_path / "site-packages" / "atdd"
    sources = collect_source_fixture_files(src_atdd)
    # Mirror only the first two; deliberately drop the third.
    dropped = sources[-1]
    for src in sources[:-1]:
        target = expected_install_path(src, src_atdd, install_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(src.read_bytes())

    missing = find_missing_fixtures(sources, src_atdd, install_dir)
    assert len(missing) == 1
    src_missing, expected_missing = missing[0]
    assert src_missing == dropped
    assert expected_missing == expected_install_path(
        dropped, src_atdd, install_dir
    )


def test_find_missing_fixtures_empty_install_dir_flags_everything(tmp_path: Path):
    """When the install dir doesn't exist at all, every source fixture is missing."""
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    install_dir = tmp_path / "site-packages" / "atdd"  # never created
    sources = collect_source_fixture_files(src_atdd)
    missing = find_missing_fixtures(sources, src_atdd, install_dir)
    assert len(missing) == len(sources)


# ---------------------------------------------------------------------------
# is_editable_install — source IS the wheel root
# ---------------------------------------------------------------------------
def test_is_editable_install_matches_when_paths_equal(monkeypatch, tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    init = src_atdd / "__init__.py"
    init.write_text("")

    fake_atdd_module_file = init

    class _FakeAtdd:
        __file__ = str(fake_atdd_module_file)

    monkeypatch.setattr(
        "atdd.coach.validators.test_wheel_completeness.atdd",
        _FakeAtdd,
    )
    assert is_editable_install(src_atdd) is True


def test_is_editable_install_false_when_paths_differ(monkeypatch, tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    (src_atdd / "__init__.py").write_text("")

    other_install = tmp_path / "site-packages" / "atdd"
    other_install.mkdir(parents=True)
    fake_init = other_install / "__init__.py"
    fake_init.write_text("")

    class _FakeAtdd:
        __file__ = str(fake_init)

    monkeypatch.setattr(
        "atdd.coach.validators.test_wheel_completeness.atdd",
        _FakeAtdd,
    )
    assert is_editable_install(src_atdd) is False


def test_is_editable_install_handles_no_source_tree():
    """When ``find_repo_src_atdd`` returned ``None`` (consumer-repo install),
    the helper must return ``False`` so the integration test can route to
    a different skip reason.
    """
    assert is_editable_install(None) is False


# ---------------------------------------------------------------------------
# build_violations — well-formed Violation records
# ---------------------------------------------------------------------------
def test_build_violations_records_wellformed(tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    install_dir = tmp_path / "site-packages" / "atdd"  # never created
    sources = collect_source_fixture_files(src_atdd)
    missing = find_missing_fixtures(sources, src_atdd, install_dir)
    violations = build_violations(missing, src_atdd)
    assert len(violations) == len(missing)
    for v in violations:
        assert v.rule_id == "coach.wheel-completeness.fixture-missing-from-wheel"
        assert v.severity == 3
        assert v.location.endswith(":1")
        assert "missing from installed wheel" in v.detail
        assert v.fix_hint_ref == "recipe:wheel-completeness#package-data"
