# URN: component:govern-lifecycle:enforcement-substrate:test_wheel_completeness_helpers:backend:domain
# Runtime: python
# Purpose: Unit tests for wheel-completeness helper functions (issues #451, #1474).

"""
Unit tests for ``test_wheel_completeness`` helper functions.

These use ``tmp_path`` to construct synthetic source-tree and install-tree layouts,
then exercise the helpers directly.

Migrated to the #1474 API. The helpers were renamed and re-scoped when the scan
stopped being about validator fixtures and started being about EVERY file in the
package:

    _is_cache_cruft              → is_excluded_from_package_data
    collect_source_fixture_files → collect_source_package_data_files
    find_missing_fixtures        → find_missing_package_data
    is_editable_install(src)     → is_editable_install(src, installed_dir)

The last one is the substantive change: the predicate used to reach for the imported
``atdd`` module through a monkeypatched global. Taking the installed directory as an
argument makes the gate's logic pure over its inputs — which is what let #1474 test
the gate itself, rather than only its parts. (The pre-#1474 gate skipped in every
environment it was ever run in, and the helper tests below could not see that,
because they never exercised the gate.)
"""

from __future__ import annotations

from pathlib import Path

import pytest

from atdd.coach.validators.test_wheel_completeness import (
    build_violations,
    collect_source_package_data_files,
    expected_install_path,
    find_missing_package_data,
    is_editable_install,
    is_excluded_from_package_data,
)


pytestmark = [pytest.mark.coach, pytest.mark.platform]


# ---------------------------------------------------------------------------
# is_excluded_from_package_data — build-artifacts the wheel must not ship
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
def test_cruft_is_excluded(path: Path):
    assert is_excluded_from_package_data(path) is True


@pytest.mark.parametrize(
    "path",
    [
        Path("foo/harness_output.json"),
        Path("foo/baz/data.yaml"),
        Path("coach/schemas/runtime-layout.md"),
        Path("coach/templates/bin/gh.shim"),
        # .py is NOT excluded (#1474): the ones under validators/fixtures/ are data,
        # not modules, and a blanket .py exclusion drops 21 of them silently.
        Path("foo/bar/test_minimal_pass.py"),
        Path("foo/bar/__init__.py"),
    ],
)
def test_shippable_files_are_not_excluded(path: Path):
    assert is_excluded_from_package_data(path) is False


# ---------------------------------------------------------------------------
# Synthetic source-tree fixture builder
# ---------------------------------------------------------------------------
def _build_synthetic_src_atdd(root: Path) -> Path:
    """A minimal ``<root>/src/atdd/...`` tree. Returns the ``src/atdd`` path.

    Carries a file from each of the shapes the #1474 scan must cover — a validator
    fixture (all the old scan could see), a schema doc (#663), a convention node
    (#1369) — with cache-cruft sprinkled alongside each.
    """
    src_atdd = root / "src" / "atdd"
    (root / "pyproject.toml").write_text("[project]\nname='synthetic-atdd'\n")

    for rel in (
        "tester/validators/fixtures/train_renders/pass/harness_output.json",
        "coach/validators/fixtures/minimal_repo/test_minimal_pass.py",
        "coach/schemas/runtime-layout.md",
        "coder/conventions/nodes/coder.dead-code.reachability.convention.yaml",
    ):
        fpath = src_atdd / rel
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text("# content\n")
        cache = fpath.parent / "__pycache__" / "stale.cpython-314.pyc"
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_bytes(b"\x00\x00")
        (fpath.parent / ".DS_Store").write_bytes(b"\x00")
    return src_atdd


# ---------------------------------------------------------------------------
# collect_source_package_data_files — walks the whole package, skips cruft
# ---------------------------------------------------------------------------
def test_collect_walks_the_whole_package_not_just_fixtures(tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    rels = sorted(
        f.relative_to(src_atdd).as_posix()
        for f in collect_source_package_data_files(src_atdd)
    )
    assert rels == [
        "coach/schemas/runtime-layout.md",
        "coach/validators/fixtures/minimal_repo/test_minimal_pass.py",
        "coder/conventions/nodes/coder.dead-code.reachability.convention.yaml",
        "tester/validators/fixtures/train_renders/pass/harness_output.json",
    ]


def test_collect_excludes_cache_cruft(tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    for f in collect_source_package_data_files(src_atdd):
        assert "__pycache__" not in f.parts
        assert f.suffix not in (".pyc", ".pyo")
        assert f.name != ".DS_Store"


def test_collect_handles_a_sparse_tree(tmp_path: Path):
    """A directory with no shippable files contributes nothing, silently."""
    src_atdd = tmp_path / "src" / "atdd"
    (src_atdd / "tester" / "validators" / "fixtures").mkdir(parents=True)
    (src_atdd / "tester" / "validators" / "fixtures" / "single.json").write_text("{}")
    (src_atdd / "planner").mkdir(parents=True)  # exists, holds nothing

    files = collect_source_package_data_files(src_atdd)
    assert [f.name for f in files] == ["single.json"]


# ---------------------------------------------------------------------------
# expected_install_path — maps src to install location
# ---------------------------------------------------------------------------
def test_expected_install_path_strips_src_atdd_prefix(tmp_path: Path):
    src_atdd = tmp_path / "src" / "atdd"
    install_dir = tmp_path / "site-packages" / "atdd"
    src_file = src_atdd / "tester/validators/fixtures/train_renders/pass/out.json"

    expected = expected_install_path(src_file, src_atdd, install_dir)

    assert expected == install_dir / "tester/validators/fixtures/train_renders/pass/out.json"
    assert expected.relative_to(install_dir) == src_file.relative_to(src_atdd)


# ---------------------------------------------------------------------------
# find_missing_package_data — diffs source tree against install location
# ---------------------------------------------------------------------------
def _mirror(sources, src_atdd: Path, install_dir: Path) -> None:
    for src in sources:
        target = expected_install_path(src, src_atdd, install_dir)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(src.read_bytes())


def test_find_missing_complete_install(tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    install_dir = tmp_path / "site-packages" / "atdd"
    sources = collect_source_package_data_files(src_atdd)
    _mirror(sources, src_atdd, install_dir)

    assert find_missing_package_data(sources, src_atdd, install_dir) == []


def test_find_missing_detects_dropped_files(tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    install_dir = tmp_path / "site-packages" / "atdd"
    sources = collect_source_package_data_files(src_atdd)
    dropped = sources[-1]
    _mirror(sources[:-1], src_atdd, install_dir)

    missing = find_missing_package_data(sources, src_atdd, install_dir)

    assert len(missing) == 1
    src_missing, expected_missing = missing[0]
    assert src_missing == dropped
    assert expected_missing == expected_install_path(dropped, src_atdd, install_dir)


def test_find_missing_empty_install_dir_flags_everything(tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    install_dir = tmp_path / "site-packages" / "atdd"  # never created
    sources = collect_source_package_data_files(src_atdd)

    assert len(find_missing_package_data(sources, src_atdd, install_dir)) == len(sources)


# ---------------------------------------------------------------------------
# is_editable_install — source IS the wheel root
# ---------------------------------------------------------------------------
def test_is_editable_install_true_when_paths_equal(tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    assert is_editable_install(src_atdd, src_atdd) is True


def test_is_editable_install_false_when_paths_differ(tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    installed = tmp_path / "site-packages" / "atdd"
    installed.mkdir(parents=True)

    assert is_editable_install(src_atdd, installed) is False


# ---------------------------------------------------------------------------
# build_violations — well-formed Violation records
# ---------------------------------------------------------------------------
def test_build_violations_records_wellformed(tmp_path: Path):
    src_atdd = _build_synthetic_src_atdd(tmp_path)
    install_dir = tmp_path / "site-packages" / "atdd"  # never created
    sources = collect_source_package_data_files(src_atdd)
    missing = find_missing_package_data(sources, src_atdd, install_dir)

    violations = build_violations(missing, src_atdd)

    assert len(violations) == len(missing)
    for v in violations:
        assert v.rule_id == "coach.wheel-completeness.fixture-missing-from-wheel"
        assert v.severity == 3
        assert v.location.endswith(":1")
        assert "missing from the installed package" in v.detail
        assert v.fix_hint_ref == "recipe:wheel-completeness#package-data"
