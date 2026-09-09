# URN: test:govern-lifecycle:govern-lifecycle:P002-UNIT-001
# Acceptance: acc:govern-lifecycle:P002-UNIT-001-the-source-bridge-still-wins-in-the-toolkit-checkout
# WMBT: wmbt:govern-lifecycle:P002
# Phase: RED
# Layer: backend.unit
# Assertion: behavioral

"""P002-UNIT-001/002 — which interpreter a hook runs its gates under.

The hooks run their gates as `python3 -c "from atdd... import _gate_main"`. pipx
and uv install atdd into an isolated venv that no ambient `python3` can import, so
in a freshly initialised consumer repo the very first `git push` is refused:

    ATDD: the python3 running this hook (/opt/homebrew/.../python3.14)
      cannot import atdd.

It is invisible in this repo because the source-checkout bridge (#928 Gap 4
Item 3) prepends `src/` to PYTHONPATH, which makes the ambient `python3` able to
import atdd — from the WORKING TREE, which is the whole point of that bridge.

That constraint is what rules out the obvious fix. Routing the gates through the
`atdd` console script would break the bridge: the script's shebang carries `-E`,
which discards PYTHONPATH, so in this repo the version gate would silently start
testing the installed wheel instead of the tree being pushed — a worse defect than
the one being fixed, and a silent one.

So the resolution is conditional, and both halves are pinned here:
  * bridge applied  -> the ambient interpreter wins, console script not consulted;
  * bridge absent   -> the interpreter behind the console script, which is the only
                       one known to hold atdd; ambient as the last resort.

The block is extracted from the template and run under a real `sh`, because it IS
shell — asserting on the Python that generates it would prove nothing about what
git executes.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach]

HOOKS = Path(__file__).resolve().parents[1]
BEGIN = "# --- BEGIN atdd-gate-interpreter ---"
END = "# --- END atdd-gate-interpreter ---"
CARRIERS = ("pre-push", "pre-merge-commit")


def _block(hook: str) -> str:
    src = (HOOKS / hook).read_text(encoding="utf-8")
    assert BEGIN in src and END in src, (
        f"{hook} carries no delimited interpreter-resolution block; the gates in it "
        f"run under whatever `python3` happens to be on PATH"
    )
    return src[src.index(BEGIN) : src.index(END) + len(END)]


def _resolve(block: str, *, bridge: bool, path_dir: Path | None, tmp_path: Path) -> str:
    """Run the block under a real sh and report the interpreter it chose."""
    script = tmp_path / "probe.sh"
    prelude = "_ATDD_SOURCE_BRIDGE=1\n" if bridge else ""
    script.write_text(f"#!/bin/sh\nset -u\n{prelude}{block}\nprintf '%s' \"$ATDD_PYTHON\"\n")
    script.chmod(0o755)

    # A MINIMAL PATH, always: inheriting the caller's would leave the developer's
    # own `atdd` discoverable and quietly turn the no-console-script case into the
    # console-script case — the test would then pass by finding a real install
    # rather than by exercising the fallback.
    env = dict(os.environ)
    env["PATH"] = f"{path_dir}:/usr/bin:/bin" if path_dir else "/usr/bin:/bin"
    return subprocess.run(
        ["sh", str(script)], capture_output=True, text=True, env=env, check=True
    ).stdout.strip()


def _fake_atdd(tmp_path: Path, interpreter: str) -> Path:
    """A console script shaped like a real one: shebang, `-E`, executable."""
    d = tmp_path / "bin"
    d.mkdir(exist_ok=True)
    script = d / "atdd"
    script.write_text(f"#!{interpreter} -E\nimport sys\n")
    script.chmod(0o755)
    return d


@pytest.mark.parametrize("hook", CARRIERS)
def test_p002_unit_001_the_source_bridge_still_wins(hook, tmp_path):
    """In the toolkit checkout the gates must keep testing the working tree."""
    decoy = tmp_path / "decoy"
    decoy.mkdir()
    (decoy / "python-decoy").write_text("")
    (decoy / "python-decoy").chmod(0o755)
    path_dir = _fake_atdd(tmp_path, str(decoy / "python-decoy"))

    chosen = _resolve(_block(hook), bridge=True, path_dir=path_dir, tmp_path=tmp_path)

    assert chosen == "python3", (
        f"{hook} resolved {chosen!r} while the source bridge was active. The bridge "
        "put the WORKING TREE on the import path; the console script's entry point "
        "carries -E and discards it, so this would silently gate the installed "
        "wheel instead of the code being pushed"
    )


@pytest.mark.parametrize("hook", CARRIERS)
def test_p002_unit_002_outside_the_bridge_the_console_script_decides(hook, tmp_path):
    """The consumer case: only the console script's interpreter holds atdd."""
    real_python = subprocess.run(
        ["sh", "-c", "command -v python3"], capture_output=True, text=True, check=True
    ).stdout.strip()
    path_dir = _fake_atdd(tmp_path, real_python)

    chosen = _resolve(_block(hook), bridge=False, path_dir=path_dir, tmp_path=tmp_path)

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

    chosen = _resolve(_block(hook), bridge=False, path_dir=empty, tmp_path=tmp_path)

    assert chosen == "python3", (
        f"{hook} resolved {chosen!r} with no atdd on PATH; it must fall back to the "
        "ambient interpreter so the gate reports the environment fault in its own "
        "words rather than the hook dying on an unset variable"
    )


@pytest.mark.parametrize("hook", CARRIERS)
def test_p002_unit_002_a_non_python_shebang_is_refused(hook, tmp_path):
    """A shell-wrapper `atdd` must not be mistaken for an interpreter."""
    path_dir = _fake_atdd(tmp_path, "/bin/sh")

    chosen = _resolve(_block(hook), bridge=False, path_dir=path_dir, tmp_path=tmp_path)

    assert chosen == "python3", (
        f"{hook} resolved {chosen!r} from a non-python shebang; some installers ship "
        "`atdd` as a shell wrapper, and running `-c 'import atdd'` under /bin/sh "
        "fails in a way that looks like a broken gate rather than a bad resolution"
    )


def test_p002_unit_001_every_carrier_holds_the_identical_block():
    """The block is duplicated across hooks; prove the copies cannot drift.

    These templates are standalone scripts with no shared-library mechanism — the
    source bridge and the emergency bypass are already copied between them the same
    way. Duplication that cannot be removed can at least be made verifiable, so a
    fix applied to one hook and forgotten in the other fails here rather than in a
    consumer's push six months later.
    """
    blocks = {hook: _block(hook) for hook in CARRIERS}
    first, *rest = blocks.items()
    for hook, block in rest:
        assert block == first[1], (
            f"the interpreter-resolution block in {hook} has drifted from "
            f"{first[0]}; they must stay byte-identical"
        )
