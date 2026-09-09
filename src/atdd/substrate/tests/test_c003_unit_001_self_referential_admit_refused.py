# URN: test:admit-substrate:substrate-admission:C003-UNIT-001-self-referential-admit-refused
# Acceptance: acc:admit-substrate:C003-UNIT-001-self-referential-admit-refused
# WMBT: wmbt:admit-substrate:C003
# Phase: GREEN
# Layer: unit
# Assertion: behavioral
"""C003-UNIT-001 — admitting a package from its own install home is refused with
the tree intact (#1840).

`install()` deleted the destination and only then read the source. When the two
were the same directory the package was destroyed and `copytree` raised
`FileNotFoundError` from `os.scandir`, leaving neither files nor a lock entry.

Measured in a disposable repo before the fix: a 53-file package went to 0 files
and the directory was gone.

The severity is not the crash. `--path <where the package already is>` is the
INTUITIVE repair after an accidental `substrate remove`, which unregisters a
package but leaves its files on disk. The destructive path was the one an
operator reaches for while trying to put something back.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from atdd.substrate.installer import SelfReferentialInstall, install, install_path


def _package(root: Path, n: int = 5) -> Path:
    src = root / "source-pkg"
    src.mkdir(parents=True)
    for i in range(n):
        (src / f"f{i}.yaml").write_text(f"payload{i}", encoding="utf-8")
    return src


def _installed(tmp_path: Path) -> Path:
    """A package genuinely installed via the real code path."""
    return install(
        _package(tmp_path),
        tmp_path / "repo",
        kind="extension",
        package_id="demo.ext",
        version="0.1.0",
    )


def test_admitting_a_package_from_its_own_home_is_refused(tmp_path):
    home = _installed(tmp_path)
    with pytest.raises(SelfReferentialInstall):
        install(home, tmp_path / "repo", kind="extension", package_id="demo.ext", version="0.1.0")


def test_the_tree_survives_the_refusal(tmp_path):
    """The point of the fix. A refusal that still deleted the files would be no fix."""
    home = _installed(tmp_path)
    before = sorted(p.name for p in home.iterdir())
    assert before, "fixture did not install anything"
    with pytest.raises(SelfReferentialInstall):
        install(home, tmp_path / "repo", kind="extension", package_id="demo.ext", version="0.1.0")
    assert home.is_dir(), "the install home was removed by a call that refused"
    assert sorted(p.name for p in home.iterdir()) == before


def test_the_refusal_names_the_path_and_says_nothing_changed(tmp_path):
    home = _installed(tmp_path)
    with pytest.raises(SelfReferentialInstall) as exc:
        install(home, tmp_path / "repo", kind="extension", package_id="demo.ext", version="0.1.0")
    message = str(exc.value)
    assert str(home) in message, "an operator cannot act on a refusal that names no path"
    assert "Nothing was changed" in message


def test_a_relative_path_naming_the_same_home_is_also_refused(tmp_path, monkeypatch):
    """Resolved comparison, not string equality — the aliases are what get typed."""
    home = _installed(tmp_path)
    monkeypatch.chdir(home.parent)
    with pytest.raises(SelfReferentialInstall):
        install(
            Path(home.name), tmp_path / "repo",
            kind="extension", package_id="demo.ext", version="0.1.0",
        )


def test_a_symlink_to_the_home_is_also_refused(tmp_path):
    home = _installed(tmp_path)
    link = tmp_path / "alias"
    link.symlink_to(home, target_is_directory=True)
    with pytest.raises(SelfReferentialInstall):
        install(link, tmp_path / "repo", kind="extension", package_id="demo.ext", version="0.1.0")


def test_ordinary_admission_from_an_external_source_still_works(tmp_path):
    """The guard must not buy safety by breaking the normal path."""
    home = _installed(tmp_path)
    assert (home / "f0.yaml").read_text(encoding="utf-8") == "payload0"
    assert home == install_path(tmp_path / "repo", "extension", "demo.ext", "0.1.0")


def test_reinstalling_from_a_different_source_still_replaces(tmp_path):
    """Idempotent replacement is the behaviour install() exists for; only the
    self-referential case is refused."""
    _installed(tmp_path)
    second = tmp_path / "second-source"
    second.mkdir()
    (second / "only.yaml").write_text("new", encoding="utf-8")
    home = install(
        second, tmp_path / "repo", kind="extension", package_id="demo.ext", version="0.1.0"
    )
    assert sorted(p.name for p in home.iterdir()) == ["only.yaml"]
