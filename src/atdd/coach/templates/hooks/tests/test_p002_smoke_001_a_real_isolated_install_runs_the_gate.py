# URN: test:govern-lifecycle:govern-lifecycle:P002-SMOKE-001
# Acceptance: acc:govern-lifecycle:P002-SMOKE-001-a-real-isolated-install-runs-the-gate
# WMBT: wmbt:govern-lifecycle:P002
# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
# Smoke: true
# # Phase: SMOKE
# # Smoke: true

"""P002-SMOKE-001 — the resolved interpreter really does import an isolated atdd.

The unit acceptances pin which string the shell picks. This one builds the
situation the string exists for: a REAL `python3 -m venv` holding an atdd the
ambient interpreter genuinely cannot import, a REAL console script with that
venv's shebang, and the REAL resolution block extracted from the hook — then runs
a gate through it and reads the verdict off stdout.

The precondition is asserted rather than assumed: if the ambient interpreter can
already import atdd, the environment cannot demonstrate isolation and the test
SKIPS. A run that passed because atdd happened to be importable everywhere would
be measuring nothing, which is the failure mode this whole issue is about.

`--without-pip` keeps venv creation to a couple of seconds; nothing here needs an
installer, because the package under import is written directly into site-packages.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = [pytest.mark.coach, pytest.mark.slow]

HOOKS = Path(__file__).resolve().parents[1]
BEGIN = "# --- BEGIN atdd-gate-interpreter ---"
END = "# --- END atdd-gate-interpreter ---"
VERDICT = "ATDD-GATE-RAN"


def _block() -> str:
    src = (HOOKS / "pre-push").read_text(encoding="utf-8")
    return src[src.index(BEGIN) : src.index(END) + len(END)]


def _isolated_atdd_venv(tmp_path: Path) -> tuple[Path, Path]:
    """A real venv holding a real (minimal) atdd, plus a real console script."""
    venv = tmp_path / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(venv)],
                   check=True, capture_output=True)
    py = venv / "bin" / "python"
    assert py.is_file(), "venv produced no interpreter"

    site = next((venv / "lib").glob("python*/site-packages"))
    pkg = site / "atdd"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "version_check.py").write_text(
        f"def _gate_main():\n    print({VERDICT!r})\n", encoding="utf-8"
    )

    bindir = tmp_path / "bin"
    bindir.mkdir()
    console = bindir / "atdd"
    console.write_text(f"#!{py} -E\nimport sys\n", encoding="utf-8")
    console.chmod(0o755)
    return venv, bindir


def test_p002_smoke_001_a_real_isolated_install_runs_the_gate(tmp_path):
    _venv, bindir = _isolated_atdd_venv(tmp_path)

    # Precondition: the ambient interpreter must NOT be able to import atdd, or
    # this environment cannot demonstrate the thing under test.
    clean = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    clean["PATH"] = f"{bindir}:/usr/bin:/bin"
    ambient = subprocess.run(["python3", "-c", "import atdd"],
                             capture_output=True, text=True, env=clean, cwd=str(tmp_path))
    if ambient.returncode == 0:
        pytest.skip("ambient python3 can already import atdd — isolation not demonstrable here")

    # The real block, then the real gate, through whatever it resolved.
    script = tmp_path / "run_gate.sh"
    script.write_text(
        "#!/bin/sh\nset -u\n"
        + _block()
        + '\n"$ATDD_PYTHON" -c "\n'
        "import sys\n"
        "try:\n"
        "    from atdd.version_check import _gate_main\n"
        "    _gate_main()\n"
        "except ImportError:\n"
        "    print('CANNOT-IMPORT', file=sys.stderr)\n"
        "    sys.exit(1)\n"
        '"\n',
        encoding="utf-8",
    )
    script.chmod(0o755)

    proc = subprocess.run(["sh", str(script)], capture_output=True, text=True,
                          env=clean, cwd=str(tmp_path))

    assert proc.returncode == 0, (
        "the gate could not run under the resolved interpreter, which is exactly "
        f"the refused-first-push the issue reports:\n{proc.stdout}{proc.stderr}"
    )
    assert VERDICT in proc.stdout, (
        f"the gate did not report a verdict:\n{proc.stdout}{proc.stderr}"
    )
    assert "CANNOT-IMPORT" not in proc.stderr
