# URN: test:govern-lifecycle:govern-lifecycle:P002-UNIT-002
# Acceptance: acc:govern-lifecycle:P002-UNIT-002-outside-the-bridge-the-console-script-decides
# WMBT: wmbt:govern-lifecycle:P002
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""P002-UNIT-002 — outside the toolkit, the console script names the interpreter.

pipx and uv install atdd into a venv no ambient python3 can import, so a freshly
initialised consumer repo could not push at all: its own pre-push hook refused the
first push. The only interpreter known to hold atdd is the one the `atdd` console
script was built against, read from its shebang.

The degradations matter as much as the happy path, because each one is a way the
hook could fail a commit for a reason the operator cannot act on: no console script
at all, a shell-wrapper `atdd`, a binary launcher, and an inherited copy of the
bridge's internal flag — that last one found while reviewing this change, and it
silently restored the original defect."""

from __future__ import annotations

import subprocess

import pytest

from atdd.coach.templates.hooks.tests._p002_interpreter_harness import (
    CARRIERS,
    _block,
    _fake_atdd,
    _resolve,
    _toolkit_checkout,
)

pytestmark = [pytest.mark.coach]


@pytest.mark.parametrize("hook", CARRIERS)
def test_p002_unit_002_outside_the_bridge_the_console_script_decides(hook, tmp_path):
    """The consumer case: only the console script's interpreter holds atdd."""
    real_python = subprocess.run(
        ["sh", "-c", "command -v python3"], capture_output=True, text=True, check=True
    ).stdout.strip()
    path_dir = _fake_atdd(tmp_path, real_python)

    chosen = _resolve(hook, repo_root=None, path_dir=path_dir, tmp_path=tmp_path)

    assert chosen == real_python, (
        f"{hook} resolved {chosen!r} rather than the interpreter behind the atdd "
        "console script — in a pipx or uv install that is the only one that can "
        "import atdd, which is why a fresh consumer repo could not push"
    )



@pytest.mark.parametrize("hook", CARRIERS)
def test_p002_unit_002_no_console_script_falls_back_to_ambient(hook, tmp_path):
    """With no atdd on PATH the gate must still run and report the fault itself."""
    empty = tmp_path / "empty"
    empty.mkdir()

    chosen = _resolve(hook, repo_root=None, path_dir=empty, tmp_path=tmp_path)

    assert chosen == "python3", (
        f"{hook} resolved {chosen!r} with no atdd on PATH; it must fall back to the "
        "ambient interpreter so the gate reports the environment fault in its own "
        "words rather than the hook dying on an unset variable"
    )



@pytest.mark.parametrize("hook", CARRIERS)
def test_p002_unit_002_a_non_python_shebang_is_refused(hook, tmp_path):
    """A shell-wrapper `atdd` must not be mistaken for an interpreter."""
    path_dir = _fake_atdd(tmp_path, "/bin/sh")

    chosen = _resolve(hook, repo_root=None, path_dir=path_dir, tmp_path=tmp_path)

    assert chosen == "python3", (
        f"{hook} resolved {chosen!r} from a non-python shebang; some installers ship "
        "`atdd` as a shell wrapper, and running `-c 'import atdd'` under /bin/sh "
        "fails in a way that looks like a broken gate rather than a bad resolution"
    )



@pytest.mark.parametrize("hook", CARRIERS)
def test_p002_unit_002_an_inherited_bridge_flag_cannot_suppress_resolution(hook, tmp_path):
    """The bridge flag is internal state; the caller's environment must not set it.

    Found in review of this change, not before it. `_ATDD_SOURCE_BRIDGE` is read
    with `${_ATDD_SOURCE_BRIDGE:-}`, so a same-named variable exported by the
    caller satisfied the guard and skipped resolution entirely — silently
    restoring the very bug this block exists to fix, in the one shape nobody
    would think to look for. The hook now clears it before the bridge can set it.
    """
    real_python = subprocess.run(
        ["sh", "-c", "command -v python3"], capture_output=True, text=True, check=True
    ).stdout.strip()
    path_dir = _fake_atdd(tmp_path, real_python)

    chosen = _resolve(hook, repo_root=None, path_dir=path_dir,
                      tmp_path=tmp_path, inherited="leaked")

    assert chosen == real_python, (
        f"{hook} resolved {chosen!r}: an inherited _ATDD_SOURCE_BRIDGE suppressed "
        "the resolution, so the gates fall back to an interpreter that cannot "
        "import an isolated atdd — the original defect, restored invisibly"
    )



@pytest.mark.parametrize("hook", CARRIERS)
def test_p002_unit_002_a_binary_console_script_is_read_boundedly(hook, tmp_path):
    """Some installers ship `atdd` as a binary launcher, not a text script."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    binary = d / "atdd"
    # No newline anywhere: an unbounded reader would scan the whole file.
    binary.write_bytes(b"\x7fELF" + b"\x00" * 200_000)
    binary.chmod(0o755)

    chosen, stderr = _resolve(hook, repo_root=None, path_dir=d, tmp_path=tmp_path,
                              want_stderr=True)

    assert chosen == "python3", (
        f"{hook} resolved {chosen!r} from a binary launcher; it must fall back "
        "rather than treat arbitrary bytes as an interpreter path"
    )
    assert stderr == "", (
        f"{hook} wrote to stderr while resolving ({stderr!r}). A binary launcher "
        "makes `sed` complain about an illegal byte sequence, and an unmuted "
        "complaint prints before every commit and push on such an install"
    )


