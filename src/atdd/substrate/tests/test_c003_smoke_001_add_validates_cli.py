# URN: test:admit-substrate:substrate-admission:C003-SMOKE-001-add-validates-cli
# Acceptance: acc:admit-substrate:C003-SMOKE-001-add-validates-cli
# WMBT: wmbt:admit-substrate:C003
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""C003-SMOKE-001 — `atdd add --path <invalid-package>` exits non-zero and installs
nothing; `atdd validate package` on a valid package still exits zero."""
from __future__ import annotations

import pathlib
import shutil

import yaml

VALID = pathlib.Path(__file__).parent / "fixtures" / "valid_extension"


def _invalid_copy(tmp_path) -> pathlib.Path:
    dst = tmp_path / "invalid_pkg"
    shutil.copytree(VALID, dst)
    m = yaml.safe_load((dst / "atdd.extension.yaml").read_text())
    m["owns"]["implementations"] = ["implementations/ghost"]  # missing owned file
    (dst / "atdd.extension.yaml").write_text(yaml.safe_dump(m, sort_keys=False))
    return dst


def test_add_invalid_refused_and_validate_package_intact(tmp_path, run_atdd) -> None:
    invalid = _invalid_copy(tmp_path)
    proc = run_atdd(["add", "--path", str(invalid)], tmp_path)
    assert proc.returncode != 0, proc.stdout + proc.stderr
    assert not (tmp_path / ".atdd" / "substrate.lock.yaml").exists()

    # admission does not regress `atdd validate package` on a valid package
    proc2 = run_atdd(["validate", "package", str(VALID)], tmp_path)
    assert proc2.returncode == 0, proc2.stdout + proc2.stderr
