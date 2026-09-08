# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""#1604 — an entry-point hook is INERT until the package is installed.

The substrate pytest plugin is auto-loaded from the ``pytest11`` entry point
declared in ``pyproject.toml``, and the #1602 smoke-execution attestation
attaches to that plugin. Entry points are read from **installed distribution
metadata** — a ``*.dist-info``/``*.egg-info`` directory found on ``sys.path`` —
and a bare source tree has none: putting ``src`` on ``PYTHONPATH`` makes
``import atdd`` work and declares nothing. Every job in this repository's own
required CI runs ``PYTHONPATH=src python3 -m pytest`` against an *uninstalled*
tree, so pytest never discovers the declaration, never loads the plugin, and any
live-smoke test run in this repo's CI records nothing.
A consumer who ran ``pip install atdd`` is unaffected, which is exactly why the
hole survived: the mechanism works everywhere except where this repo exercises
it.

Three layers, because each is independently droppable:

1. **The declaration** — ``pyproject.toml`` still declares the substrate plugin
   under ``pytest11``. Delete it and nothing auto-loads in any consumer.
2. **The CI path** — the ``attestation-hook-install`` job installs the package
   BEFORE it runs pytest, runs pytest with no ``PYTHONPATH=src``, and is demanded
   by the ``validate-gate`` fan-in. A job nobody demands blocks nothing.
3. **The causal claim itself** — the slow test at the bottom builds one virtualenv
   and runs the SAME source through it twice: once with the distribution
   installed, once reachable only via ``PYTHONPATH``. Same interpreter, same
   dependency set, same package source; the only difference is the metadata. The
   hook loads in the first and not in the second. That is #1604 in one test, and
   it is what makes the CI change above a fix rather than an assertion.

And one guard that runs *in* the CI job: the job exports
``ATDD_HOOK_MUST_BE_INSTALLED=1``, and
:func:`test_this_pytest_process_loaded_the_hook_exactly_when_its_environment_declares_it`
turns that into a hard requirement on the running process. Reverting the job to
``PYTHONPATH=src`` therefore reds the job itself, not just the YAML reader —
the fix cannot be undone quietly at either end.

SCOPE (#1604 is the install-enablement, not the CI-width redesign). This does not
decide *which* smoke tests run under the installed interpreter, and it does not
touch ``.github/atdd-merge-authority-policy.yaml`` or its required-status-context
set. It establishes the installed path and proves the hook fires there; the
selection of smoke work to run on it is the deferred operator decision.

NOTE for whoever lands #1602 here: the attestation hook itself is not on this
branch (``atdd.tester.substrate.smoke_attestation`` does not exist yet), so the
observable below is the plugin's *activation* — the single mechanism the
attestation rides on — rather than an attestation record. When the hook lands,
the honest extension is to add an anchored ``live_smoke`` probe to the two arms
below and assert the store record, not to replace this: activation is the part
that #1604 was actually about.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pytest
import yaml

#: ``tests/ci_install/<this file>`` — resolved from the file, not the cwd, so the
#: readers below describe the checkout they ship in whatever directory pytest ran from.
REPO_ROOT = Path(__file__).resolve().parents[2]
PYPROJECT = REPO_ROOT / "pyproject.toml"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "atdd-validate.yml"

#: The module the substrate plugin (and, from #1602, the attestation hook) lives in.
SUBSTRATE_MODULE = "atdd.tester.substrate.plugin"

#: The CI job that installs the package before running pytest — the #1604 fix.
INSTALL_JOB = "attestation-hook-install"

#: The fan-in job whose success is this repository's merge check.
GATE_JOB = "validate-gate"

#: Exported by ``INSTALL_JOB``; makes "the hook is loaded" a hard requirement there.
MUST_BE_INSTALLED_ENV = "ATDD_HOOK_MUST_BE_INSTALLED"

#: ``src/atdd/__init__.py`` falls back to this when ``importlib.metadata`` finds no
#: distribution — i.e. it is the version you see precisely when the entry point is
#: undiscoverable. A second, independent read on the same cause.
UNINSTALLED_VERSION = "0.0.0"


# --------------------------------------------------------------------------- #
# Readers — the declaration and the CI wiring                                  #
# --------------------------------------------------------------------------- #
def _load_toml(path: Path) -> Dict[str, Any]:
    try:
        import tomllib  # type: ignore[import-not-found]
    except ImportError:  # Python < 3.11
        import tomli as tomllib  # type: ignore[import-not-found]
    with open(path, "rb") as fh:
        return tomllib.load(fh)


def declared_pytest11_entry_points() -> Dict[str, str]:
    """``{entry-point name: module}`` as this repo declares them. Read, never assumed."""
    data = _load_toml(PYPROJECT)
    project = data.get("project") if isinstance(data, dict) else None
    entry_points = project.get("entry-points") if isinstance(project, dict) else None
    pytest11 = entry_points.get("pytest11") if isinstance(entry_points, dict) else None
    return dict(pytest11) if isinstance(pytest11, dict) else {}


def substrate_entry_point_name() -> str:
    """The name pytest registers the substrate plugin under, read from pyproject.

    pytest registers an entry-point plugin under the entry point's *name*, so this
    string is what ``has_plugin()`` and ``-p no:<name>`` both key on. Deriving it
    from the declaration means renaming the entry point cannot leave these tests
    passing against a name nothing loads.
    """
    for name, module in declared_pytest11_entry_points().items():
        if module == SUBSTRATE_MODULE:
            return name
    raise AssertionError(
        f"{PYPROJECT} declares no pytest11 entry point for {SUBSTRATE_MODULE!r} — "
        f"nothing auto-loads the substrate plugin (and with it the smoke attestation) "
        f"in an installed consumer. declared: {declared_pytest11_entry_points()}"
    )


def _jobs() -> Dict[str, Any]:
    data = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8")) or {}
    jobs = data.get("jobs") if isinstance(data, dict) else None
    return jobs if isinstance(jobs, dict) else {}


def _steps(job_id: str) -> List[Dict[str, Any]]:
    job = _jobs().get(job_id)
    steps = job.get("steps") if isinstance(job, dict) else None
    return [s for s in steps if isinstance(s, dict)] if isinstance(steps, list) else []


def _run(step: Dict[str, Any]) -> str:
    return str(step.get("run") or "")


def _first_step_index(job_id: str, predicate) -> Optional[int]:
    for index, step in enumerate(_steps(job_id)):
        if predicate(_run(step)):
            return index
    return None


def _installs_this_project(run: str) -> bool:
    """A step that installs THIS checkout — ``pip install -e .`` or a built wheel."""
    if "pip" not in run or "install" not in run:
        return False
    return "-e ." in run or ".whl" in run


def _runs_pytest(run: str) -> bool:
    return "pytest" in run


def install_job_is_required_by_the_gate() -> bool:
    """Whether ``validate-gate`` both NEEDS the install job and CHECKS its result.

    Both halves, because ``validate-gate`` is ``if: always()``: a job sitting in
    ``needs`` whose result is never inspected does not fail the gate, so reading
    ``needs`` alone would report a gate that cannot block as if it could. Same
    predicate the #1428 enforce gate is held to (``atdd.enforce.ci_gate``).
    """
    gate = _jobs().get(GATE_JOB)
    if not isinstance(gate, dict):
        return False
    needs = gate.get("needs")
    needs = [needs] if isinstance(needs, str) else needs
    if not isinstance(needs, list) or INSTALL_JOB not in needs:
        return False
    steps = gate.get("steps") if isinstance(gate.get("steps"), list) else []
    return any(
        f"needs.{INSTALL_JOB}.result" in _run(step)
        for step in steps
        if isinstance(step, dict)
    )


# --------------------------------------------------------------------------- #
# Layer 1 — the declaration                                                    #
# --------------------------------------------------------------------------- #
def test_the_substrate_plugin_is_declared_as_a_pytest11_entry_point() -> None:
    """The declaration IS the activation mechanism in an installed consumer."""
    assert SUBSTRATE_MODULE in declared_pytest11_entry_points().values(), (
        f"{SUBSTRATE_MODULE} is no longer a pytest11 entry point — nothing auto-loads "
        f"the substrate plugin, so the smoke attestation is inert in every consumer "
        f"and installing the package in CI would fix nothing. "
        f"declared: {declared_pytest11_entry_points()}"
    )


# --------------------------------------------------------------------------- #
# Layer 2 — the CI path                                                        #
# --------------------------------------------------------------------------- #
def test_the_install_job_installs_the_package_before_it_runs_pytest() -> None:
    """Install first, then pytest — in that order, with no ``PYTHONPATH=src``.

    Order is the whole content of the claim. pytest reads entry points once, at
    startup, from the metadata present *then*: a pytest step that precedes the
    install runs against exactly the environment #1604 is about.
    """
    assert INSTALL_JOB in _jobs(), (
        f"{WORKFLOW.name} has no {INSTALL_JOB!r} job — no CI path installs the package, "
        f"so the pytest11 hook is loaded by nothing in this repo's own CI"
    )

    install_at = _first_step_index(INSTALL_JOB, _installs_this_project)
    pytest_at = _first_step_index(INSTALL_JOB, _runs_pytest)

    assert install_at is not None, (
        f"{INSTALL_JOB} never installs this checkout (`pip install -e .` or a built "
        f"wheel) — without installed distribution metadata pytest cannot discover the "
        f"pytest11 entry point, whatever else the job runs"
    )
    assert pytest_at is not None, f"{INSTALL_JOB} runs no pytest, so it proves nothing"
    assert install_at < pytest_at, (
        f"{INSTALL_JOB} runs pytest (step {pytest_at}) BEFORE it installs the package "
        f"(step {install_at}) — pytest reads entry points at startup, so that run is "
        f"uninstalled and the hook is inert in it"
    )

    pytest_run = _run(_steps(INSTALL_JOB)[pytest_at])
    assert "PYTHONPATH" not in pytest_run, (
        f"{INSTALL_JOB}'s pytest step sets PYTHONPATH:\n  {pytest_run.strip()}\n"
        f"That is the uninstalled invocation this job exists to be the alternative to. "
        f"The installed package is already importable; adding PYTHONPATH only makes the "
        f"job resemble the ones that cannot load the hook."
    )

    job_env = _jobs()[INSTALL_JOB].get("env") or {}
    assert str(job_env.get(MUST_BE_INSTALLED_ENV)) == "1", (
        f"{INSTALL_JOB} does not export {MUST_BE_INSTALLED_ENV}=1, so the in-process "
        f"guard downgrades to a consistency check and the job would stay green if the "
        f"install silently stopped taking effect"
    )


def test_the_install_job_is_demanded_by_the_validate_gate_fan_in() -> None:
    """A job the required gate does not demand can go red and the merge lands anyway."""
    assert install_job_is_required_by_the_gate(), (
        f"{GATE_JOB} does not require {INSTALL_JOB!r} — it must BOTH list it in `needs` "
        f"AND inspect `needs.{INSTALL_JOB}.result`, because the gate runs `if: always()` "
        f"and a needs entry alone is decorative. As wired, the one CI path that can load "
        f"the smoke attestation hook is advisory."
    )


# --------------------------------------------------------------------------- #
# The in-process guard — runs inside the install job                           #
# --------------------------------------------------------------------------- #
def _distribution_metadata_present() -> bool:
    from importlib.metadata import PackageNotFoundError, distribution

    try:
        distribution("atdd")
    except PackageNotFoundError:
        return False
    return True


def test_this_pytest_process_loaded_the_hook_exactly_when_its_environment_declares_it(
    pytestconfig: pytest.Config,
) -> None:
    """What the YAML claims, asserted from inside the process the YAML started.

    In the install job (``ATDD_HOOK_MUST_BE_INSTALLED=1``) this is unconditional:
    the plugin MUST be loaded. Revert that job to an uninstalled invocation and the
    job reds here, not merely in the YAML reader above — the job cannot lie about
    its own environment.

    Anywhere else (a developer's checkout, installed or not) the general invariant
    is asserted instead: the plugin is loaded **if and only if** this environment
    carries atdd's distribution metadata. That biconditional is not merely
    plausible, it follows from the order pytest does things in —
    ``Config._preparse`` calls ``_configure_python_path()`` (which applies this
    repo's ``pythonpath = ["src"]``) *before* ``load_setuptools_entrypoints()``, so
    autoload and the reader below see the same ``sys.path``. Which also explains a
    result that otherwise looks like a contradiction of #1604: in a tree where an
    earlier ``pip install -e .`` left an ``src/atdd.egg-info`` behind, even a
    ``PYTHONPATH=src`` run loads the plugin, because that leftover IS distribution
    metadata. A fresh CI checkout has no such directory, which is why the toolkit's
    uninstalled jobs load nothing.

    Never skipped in either branch: a skip here is the shape of the bug this file
    is about.
    """
    name = substrate_entry_point_name()
    loaded = pytestconfig.pluginmanager.has_plugin(name)

    if os.environ.get(MUST_BE_INSTALLED_ENV) == "1":
        assert loaded, (
            f"{MUST_BE_INSTALLED_ENV}=1 but pytest did not load {name!r}. This process "
            f"is not running against an installed atdd (or plugin autoload is disabled), "
            f"so the smoke attestation hook is inert in it — which is #1604, unfixed. "
            f"atdd metadata discoverable now: {_distribution_metadata_present()}"
        )
        return

    assert loaded == _distribution_metadata_present(), (
        f"pytest loaded {name!r}: {loaded}, but atdd distribution metadata discoverable: "
        f"{_distribution_metadata_present()}. Installed metadata is the only route the "
        f"entry point has, and autoload reads the same sys.path this check does — so a "
        f"mismatch means something other than the declaration decided whether the hook "
        f"runs (plugin autoload disabled, or `-p no:{name}`)."
    )


# --------------------------------------------------------------------------- #
# Layer 3 — the causal claim, through a real install                           #
# --------------------------------------------------------------------------- #
#: The probe reports on the pytest process that loaded it. It asserts nothing: the
#: verdict belongs to the test below, which sees BOTH arms and can therefore tell
#: "the hook did not load" apart from "the run never happened".
PROBE_SOURCE = '''\
"""Reports how the pytest process that collected it was assembled."""
import json
import os
import sys
from importlib.metadata import distributions


def _atdd_metadata_paths():
    """Every discoverable `atdd` distribution, by the path its metadata sits at.

    This is the variable under test, read directly: pytest's autoload walks the
    same distributions and registers the `pytest11` entry points it finds. An
    `*.egg-info` left in a source tree counts, which is exactly the confound the
    caller's PYTHONPATH arm is built to avoid.
    """
    found = []
    for dist in distributions():
        name = (dist.metadata["Name"] or "").lower().replace("-", "_")
        if name == "atdd":
            found.append(str(getattr(dist, "_path", dist.locate_file(""))))
    return sorted(found)


def test_probe(pytestconfig):
    plugin = pytestconfig.pluginmanager.get_plugin(os.environ["ATDD_PROBE_PLUGIN_NAME"])
    try:
        import atdd

        atdd_realfile = os.path.realpath(atdd.__file__)
        atdd_version = getattr(atdd, "__version__", None)
        import_error = None
    except Exception as exc:  # pragma: no cover - reported, not raised
        atdd_realfile = None
        atdd_version = None
        import_error = f"{type(exc).__name__}: {exc}"

    with open(os.environ["ATDD_PROBE_OUT"], "w", encoding="utf-8") as fh:
        json.dump(
            {
                "substrate_loaded": plugin is not None,
                "plugin_module": getattr(plugin, "__name__", None),
                "atdd_realfile": atdd_realfile,
                "atdd_version": atdd_version,
                "atdd_metadata_paths": _atdd_metadata_paths(),
                "import_error": import_error,
                "executable": sys.executable,
            },
            fh,
        )
'''


def _venv_python(venv: Path) -> Path:
    bindir = "Scripts" if os.name == "nt" else "bin"
    return venv / bindir / ("python.exe" if os.name == "nt" else "python")


def _clean_env(**overrides: str) -> Dict[str, str]:
    """This process's environment minus everything that would smuggle atdd in.

    ``PYTHONPATH`` is the load-bearing removal and it matters for pip as much as
    for pytest: the toolkit's own suite runs under ``PYTHONPATH=src``, an editable
    install leaves an ``src/atdd.egg-info`` behind, and a ``pip uninstall`` that
    inherits that PYTHONPATH resolves the distribution to the source tree's
    ``egg-info``, reports success, and leaves the venv's real ``dist-info`` in
    place — so arm 2 would silently still be installed.
    """
    env = {
        k: v
        for k, v in os.environ.items()
        if k
        not in {
            "PYTHONPATH",
            "PYTEST_ADDOPTS",
            "PYTEST_PLUGINS",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD",
            MUST_BE_INSTALLED_ENV,
        }
    }
    env.update(overrides)
    return env


def _pip(python: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(python), "-m", "pip", "--disable-pip-version-check", *args],
        capture_output=True,
        text=True,
        env=_clean_env(),
        timeout=1800,
    )


def _run_probe(
    python: Path,
    probe_dir: Path,
    out: Path,
    plugin_name: str,
    pythonpath: Optional[Path] = None,
) -> Tuple[subprocess.CompletedProcess, Optional[Dict[str, Any]]]:
    """Run the probe under ``python`` and return (process, report or None)."""
    env = _clean_env(ATDD_PROBE_OUT=str(out), ATDD_PROBE_PLUGIN_NAME=plugin_name)
    if pythonpath is not None:
        env["PYTHONPATH"] = str(pythonpath)

    if out.exists():
        out.unlink()

    proc = subprocess.run(
        [str(python), "-m", "pytest", str(probe_dir), "-q", "-p", "no:cacheprovider"],
        cwd=str(probe_dir),
        capture_output=True,
        text=True,
        env=env,
        timeout=900,
    )
    report = json.loads(out.read_text(encoding="utf-8")) if out.exists() else None
    return proc, report


@pytest.fixture
def _editable_build_residue() -> Any:
    """Leave the checkout as we found it after an editable install writes to it.

    ``pip install -e .`` has setuptools write ``src/atdd.egg-info`` into the source
    tree. In CI that is ephemeral; in a developer's checkout it persists, and because
    pytest applies ini ``pythonpath`` before autoloading entry points, an ``egg-info``
    sitting in ``src/`` makes every later ``PYTHONPATH=src`` run load the plugin — a
    difference in test-suite behaviour caused by nothing but a stale build artifact.
    Removed only when this test created it, and only when it is what its name says.
    """
    residue = REPO_ROOT / "src" / "atdd.egg-info"
    pre_existing = residue.exists()
    try:
        yield residue
    finally:
        if not pre_existing and residue.is_dir() and residue.name.endswith(".egg-info"):
            shutil.rmtree(residue, ignore_errors=True)


@pytest.mark.smoke
def test_installed_metadata_loads_the_hook_and_pythonpath_alone_does_not(
    tmp_path: Path,
    _editable_build_residue: Path,
) -> None:
    """The #1604 claim, run: one interpreter, one package, two kinds of reachability.

    A single virtualenv is used for both arms and the package is installed with
    ``pip install -e .`` — the command the CI job runs — so the arms differ in the
    one variable under test:

      * arm 1: the distribution is INSTALLED; pytest discovers the ``pytest11``
        entry point from its metadata and loads the substrate plugin;
      * arm 2: the distribution is UNINSTALLED and the identical package source is
        reachable only through ``PYTHONPATH`` — ``import atdd`` succeeds, and pytest
        loads nothing. This is the toolkit's own CI today.

    Arm 2 deliberately points ``PYTHONPATH`` at a directory holding a link to
    ``src/atdd`` rather than at ``src`` itself, because ``src`` is not reliably free
    of metadata: an editable install writes ``src/atdd.egg-info``, that directory IS
    distribution metadata wherever it can be reached, and arm 1 above (like the CI
    job's own install step) creates one. Pointed at ``src``, arm 2 would pass for a
    reason a fresh CI checkout never has. The link reproduces the fresh checkout —
    same source, no metadata — and :func:`_editable_build_residue` removes the
    residue afterwards so the developer's tree is left as it was found. That residue
    is not cosmetic: pytest applies ini ``pythonpath`` BEFORE it autoloads entry
    points, so an ``egg-info`` left in ``src/`` quietly turns every subsequent
    ``PYTHONPATH=src`` run in the checkout into a plugin-loading one.
    """
    plugin_name = substrate_entry_point_name()

    venv = tmp_path / "venv"
    created = subprocess.run(
        [sys.executable, "-m", "venv", str(venv)],
        capture_output=True,
        text=True,
        env=_clean_env(),
        timeout=600,
    )
    assert created.returncode == 0, f"could not create a venv:\n{created.stderr}"
    python = _venv_python(venv)

    probe_dir = tmp_path / "probe"
    probe_dir.mkdir()
    (probe_dir / "test_hook_probe.py").write_text(PROBE_SOURCE, encoding="utf-8")
    out = tmp_path / "report.json"

    # --- arm 1: installed ---------------------------------------------------
    install = _pip(python, "install", "-e", str(REPO_ROOT))
    assert install.returncode == 0, (
        f"`pip install -e .` failed — the CI job's install step would fail the same "
        f"way:\n{install.stdout}\n{install.stderr}"
    )
    proc, installed = _run_probe(python, probe_dir, out, plugin_name)
    assert proc.returncode == 0 and installed is not None, (
        f"the probe did not run against the installed package:\n{proc.stdout}\n{proc.stderr}"
    )

    assert installed["substrate_loaded"] is True, (
        f"atdd is installed and pytest still did not load {plugin_name!r} — the "
        f"pytest11 declaration no longer activates the plugin, so installing the "
        f"package in CI buys nothing. probe: {installed}"
    )
    assert installed["plugin_module"] == SUBSTRATE_MODULE, (
        f"pytest loaded {plugin_name!r} but it is not {SUBSTRATE_MODULE} — the smoke "
        f"attestation hook lives in that module; anything else is a different plugin. "
        f"probe: {installed}"
    )
    assert installed["import_error"] is None, f"probe could not import atdd: {installed}"
    assert installed["atdd_metadata_paths"], (
        f"the installed arm found no atdd distribution metadata at all, yet the plugin "
        f"loaded — the arms are not measuring what this test says they measure. "
        f"probe: {installed}"
    )

    # --- arm 2: same source, reachable only by PYTHONPATH -------------------
    uninstall = _pip(python, "uninstall", "-y", "atdd")
    assert uninstall.returncode == 0, (
        f"could not uninstall atdd:\n{uninstall.stdout}\n{uninstall.stderr}"
    )

    src_link_dir = tmp_path / "pythonpath"
    src_link_dir.mkdir()
    package = REPO_ROOT / "src" / "atdd"
    try:
        (src_link_dir / "atdd").symlink_to(package, target_is_directory=True)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform guard
        raise AssertionError(f"cannot link {package} for the PYTHONPATH arm: {exc}") from exc

    proc, uninstalled = _run_probe(python, probe_dir, out, plugin_name, pythonpath=src_link_dir)
    assert proc.returncode == 0 and uninstalled is not None, (
        f"the PYTHONPATH probe did not run — 'the hook was not loaded' must not be a "
        f"synonym for 'nothing ran':\n{proc.stdout}\n{proc.stderr}"
    )
    assert uninstalled["import_error"] is None, (
        f"PYTHONPATH did not make atdd importable, so this arm says nothing about entry "
        f"points: {uninstalled}"
    )
    assert uninstalled["atdd_realfile"] == str(package / "__init__.py"), (
        f"the PYTHONPATH arm imported a different atdd than the installed arm — the two "
        f"arms must differ only in metadata. probe: {uninstalled}"
    )

    assert uninstalled["atdd_metadata_paths"] == [], (
        f"this arm is supposed to have NO atdd distribution metadata, and it found "
        f"{uninstalled['atdd_metadata_paths']}. An `*.egg-info`/`*.dist-info` reachable "
        f"from a path entry IS installed metadata, so the arm would prove the opposite "
        f"of what it claims. probe: {uninstalled}"
    )
    assert uninstalled["substrate_loaded"] is False, (
        f"pytest loaded {plugin_name!r} with no atdd distribution metadata discoverable "
        f"anywhere — something other than the pytest11 entry point is loading the "
        f"plugin, and #1604's premise is wrong. probe: {uninstalled}"
    )
    assert uninstalled["atdd_version"] == UNINSTALLED_VERSION, (
        f"atdd.__version__ is {uninstalled['atdd_version']!r}, not the "
        f"{UNINSTALLED_VERSION!r} that importlib.metadata falls back to when no "
        f"distribution is found — the second reading disagrees that this arm is "
        f"uninstalled. probe: {uninstalled}"
    )
