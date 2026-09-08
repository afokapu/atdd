"""Read what this repository's CI would actually EXECUTE (#1664 axis 3, #1814).

Split out of :mod:`atdd.tester.substrate.attestability` in #1814, when that module
passed the 500-line report threshold. The seam is the one #1664 already drew in
prose: axes 1 and 2 are properties of the ACCEPTANCE and its anchored test, and
are decided from `plan/` and a test header. Axis 3 is a property of the RUNNER —
which paths a workflow hands pytest, whether the job installs the distribution,
and which environment variables it defines. Different inputs, different reasons to
change, and only the classifier needs both.

NOTHING HERE RUNS A TEST. Attestation is written by a pytest11 entry point, so a
reader that executed tests to decide capability would be classifying its own
runner rather than the repository's: the same test writes an attestation under an
installed dist and none under `PYTHONPATH=src`, and BOTH report passed. Every
input is a document.
"""
from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

import yaml

_logger = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Axis 3: is the anchored test on a path CI actually runs, under a runner that
# loads the plugin? (#1664 team finding, 2026-09-07)
#
# THIS CLASSIFIER NEVER RUNS A TEST. Attestation is written by a pytest11 entry
# point, so a classifier that executed tests to decide capability would classify
# its own runner rather than the acceptance: the same test writes an attestation
# under the installed dist and writes none under `PYTHONPATH=src`, and BOTH
# report passed. Every input here is static — workflow text and file paths.
# --------------------------------------------------------------------------- #

#: A shell line continuation: a trailing backslash and the indentation after it.
#: Joined before scanning because a multi-line `run:` block is ONE command, and a
#: reader that scanned it line-by-line would see `pytest \` with no argument and
#: report the job as running nothing. Measured on main at b43ec91c: that is
#: `regression-suite-test`, whose 19 paths — `src/atdd/state/tests`,
#: `src/atdd/coach/gate`, `src/atdd/coach/handlers` among them — were the bulk of
#: what CI actually runs and were being censused as `not-run-by-ci` (#1604).
_LINE_CONTINUATION = re.compile(r"\\\s*\n\s*")

#: Every path argument of a pytest invocation, not just the first. `pytest a b c`
#: is one step running three targets; a single-capture reader keeps `a` and drops
#: the rest, which understates coverage exactly where a job covers most ground.
_CI_PYTEST_TARGET = re.compile(r"(?<![\w./-])((?:src|tests)/[A-Za-z0-9_./-]*)")

#: A CI step that installs the distribution, which is what writes the dist-info
#: pytest's entry-point discovery reads. `PYTHONPATH=src` never does.
_CI_INSTALLS_DIST = re.compile(r"pip3?\s+install[^\n]*(-e\s+\.|dist/\*\.whl|\.\[)")

#: An invocation that hands pytest an explicit import path, i.e. the uninstalled
#: spelling #1604 is about. Read so a step can be reported as running WITHOUT the
#: metadata even when some other step of the same job installed the package.
_SETS_PYTHONPATH = re.compile(r"\bPYTHONPATH\s*=")


@dataclass(frozen=True)
class CiPytestStep:
    """One workflow step that runs pytest over paths inside this checkout.

    ``installs_dist`` is a property of the JOB, not of this step: the install and
    the pytest call are different steps, so a per-step reading would report the
    one job that does install as though it did not. ``sets_pythonpath`` is a
    property of the step itself, because that is where the defect is spelled.
    """

    workflow: str
    job: str
    step: str
    targets: Tuple[str, ...]
    installs_dist: bool
    sets_pythonpath: bool


def _job_steps(workflow_texts: Dict[str, str]) -> "List[Tuple[str, str, List[Tuple[str, str]]]]":
    """``(workflow, job, [(step name, run text)])`` for every job in every file.

    Parsed as YAML rather than split on indentation: `run: >-` folds its
    continuation lines into the command, and a text split cannot fold. Still
    static — a document is read, no test and no workflow is executed.
    """
    out: List[Tuple[str, str, List[Tuple[str, str]]]] = []
    for name, text in workflow_texts.items():
        try:
            doc = yaml.safe_load(text) or {}
        except yaml.YAMLError:  # a malformed workflow classifies nothing, it does not crash
            continue
        jobs = doc.get("jobs") if isinstance(doc, dict) else None
        if not isinstance(jobs, dict):
            continue
        for job_id, job in jobs.items():
            steps = job.get("steps") if isinstance(job, dict) else None
            if not isinstance(steps, list):
                continue
            runs = [
                (str(s.get("name") or ""), str(s.get("run") or ""))
                for s in steps
                if isinstance(s, dict) and s.get("run")
            ]
            out.append((name, str(job_id), runs))
    return out


def _pytest_target_lines(run: str) -> List[Tuple[str, Tuple[str, ...]]]:
    """Each pytest invocation in one ``run`` block, as ``(text before `pytest`, targets)``.

    A ``run:`` block is a script, so reading workflows -> steps -> lines is three
    nested loops in one function and lands straight on the nesting ratchet — the
    same shape #1664 extracted ``_train_entries`` to avoid. The text BEFORE the
    command is what comes back rather than the whole line, because the only thing
    the caller asks of it is whether the invocation sets ``PYTHONPATH``, and an
    environment prefix can only precede the command it applies to.
    """
    lines: List[Tuple[str, Tuple[str, ...]]] = []
    for line in run.splitlines():
        head, sep, tail = line.partition("pytest")
        if not sep:
            continue
        targets = tuple(t.rstrip("/") for t in _CI_PYTEST_TARGET.findall(tail))
        if targets:
            lines.append((head, targets))
    return lines


def _job_pytest_steps(
    workflow: str, job: str, runs: "List[Tuple[str, str]]"
) -> List[CiPytestStep]:
    """One job's pytest steps, with the job-level install verdict stamped on each.

    ``installs`` is computed once over the whole job and shared, because the
    install and the pytest call are different steps: deciding it per step would
    report the one job that does install as though it did not.
    """
    joined = [(step, _LINE_CONTINUATION.sub(" ", run)) for step, run in runs]
    installs = any(_CI_INSTALLS_DIST.search(run) for _, run in joined)
    found: List[CiPytestStep] = []
    for step, run in joined:
        for head, targets in _pytest_target_lines(run):
            found.append(
                CiPytestStep(
                    workflow=workflow,
                    job=job,
                    step=step,
                    targets=targets,
                    installs_dist=installs,
                    sets_pythonpath=bool(_SETS_PYTHONPATH.search(head)),
                )
            )
    return found


def ci_pytest_steps(workflow_texts: Dict[str, str]) -> List[CiPytestStep]:
    """Every workflow step that runs pytest over `src/` or `tests/` paths.

    The unit is the STEP, so a job can be reported honestly when one of its
    pytest calls is installed and another is not.
    """
    found: List[CiPytestStep] = []
    for workflow, job, runs in _job_steps(workflow_texts):
        found.extend(_job_pytest_steps(workflow, job, runs))
    return found


def ci_pytest_targets(workflow_texts: Dict[str, str]) -> Dict[str, bool]:
    """Map each CI pytest target path to whether its job installs the dist.

    A target whose job never installs the package cannot load the attestation
    plugin, so a test under it produces no evidence however green it runs.
    """
    targets: Dict[str, bool] = {}
    for step in ci_pytest_steps(workflow_texts):
        for path in step.targets:
            targets[path] = targets.get(path, False) or step.installs_dist
    return targets


#: Runner verdicts — all four describe the INVOCATION, and none claims evidence.
#:
#: These were named ``ci-can-record`` / ``ci-runs-cannot-record`` until #1815
#: measured what a CI run actually produces: nothing. A CI-shaped checkout
#: resolves its Control Root inside the workspace, creates a store there, and
#: records zero events against zero work items — the attestation is keyed by
#: work-item uid and work items are written by ``atdd worktree create`` into a
#: DEVELOPER's Control Root, so a CI checkout has no identity to key one to. The
#: writer says so itself: "this branch resolves to no registered work item".
#:
#: So "can record" was never true of any value here, and naming one of them that
#: is how a reader concludes CI could discharge the SMOKE obligation. What this
#: axis really knows is whether the hook LOADS — whether the invocation installs
#: the distribution and whether the test deselects itself — and the names now say
#: only that.
CI_RUNS_WITH_HOOK = "ci-runs-with-hook"
CI_RUNS_WITHOUT_HOOK = "ci-runs-without-hook"
CI_TEST_OPTS_OUT = "ci-runs-but-test-opts-out"
NOT_RUN_BY_CI = "not-run-by-ci"

#: Attribute names that read the environment: ``os.getenv(X)``,
#: ``os.environ.get(X)``, ``os.environ[X]``.
_ENV_READERS = frozenset({"getenv", "get"})


def _string_literal(node: object) -> Optional[str]:
    """The value of a string-literal node, or None for anything computed.

    Only literals count. An environment name assembled at run time is not
    derivable from the source, and guessing at one would be the self-attestation
    this substrate exists to avoid — it simply does not register as a gate.
    """
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _env_name_from_call(node: ast.AST) -> Optional[str]:
    """``os.getenv("X")`` / ``os.environ.get("X")`` -> ``"X"``."""
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
        return None
    if node.func.attr not in _ENV_READERS or not node.args:
        return None
    owner = ast.unparse(node.func.value)
    if "environ" not in owner and owner != "os":
        return None
    return _string_literal(node.args[0])


def _env_name_from_subscript(node: ast.AST) -> Optional[str]:
    """``os.environ["X"]`` -> ``"X"``."""
    if not isinstance(node, ast.Subscript) or "environ" not in ast.unparse(node.value):
        return None
    return _string_literal(node.slice)


def _env_names_read(node: ast.AST) -> Set[str]:
    """Every environment variable name an expression reads, by either spelling."""
    names = set()
    for child in ast.walk(node):
        for reader in (_env_name_from_call, _env_name_from_subscript):
            name = reader(child)
            if name is not None:
                names.add(name)
    return names


def skip_env_gates(source: str) -> Set[str]:
    """Environment variables whose absence deselects tests in this module.

    Read from ``pytestmark`` and from per-test decorators, because both deselect
    and only one of them is module-wide.

    Deliberately narrower than "has a skipif". Measured on main: 8 SMOKE
    acceptances carry a module-level skip and 6 of them gate on
    ``shutil.which("git") is None``, which is satisfied on every CI runner — so a
    blanket skipif rule would report three-quarters of them as unreachable when
    they run fine. An ENVIRONMENT gate is different in kind: whether it is
    satisfied is a property of the runner, and the runner's environment is
    something this module can read (:func:`ci_env_names`). That makes the pairing
    decidable instead of guessed, and self-correcting — set the variable in a job
    and the verdict flips with no edit here.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        # Reported, not swallowed: a test file this reader cannot parse is a file
        # whose gates are invisible to the census, so it would be scored as
        # ungated — the optimistic direction. Rare enough to be a debug line and
        # important enough not to be silent.
        _logger.debug(
            "ci runner: source does not parse, so no skip gate can be read from it: %s",
            exc,
            extra={"error_type": type(exc).__name__},
        )
        return set()

    found: Set[str] = set()

    def scan(node: ast.AST) -> None:
        for child in ast.walk(node):
            if (
                isinstance(child, ast.Call)
                and isinstance(child.func, ast.Attribute)
                and child.func.attr in ("skipif", "skip")
                and child.args
            ):
                found.update(_env_names_read(child.args[0]))

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "pytestmark"
            for target in node.targets
        ):
            scan(node.value)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for decorator in node.decorator_list:
                scan(decorator)
    return found


def ci_env_names(workflow_texts: Dict[str, str]) -> Set[str]:
    """Every environment variable name any workflow sets, at any level.

    Workflow, job and step ``env:`` blocks are merged: which job sets a variable
    does not matter to the question asked here, which is whether the repository's
    CI defines it at all. Erring wide is the safe direction — it can only ever
    report a test as reachable that a narrower read would call gated, and a
    false "reachable" is visible the moment the test is added to a job.
    """
    names: Set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            env = node.get("env")
            if isinstance(env, dict):
                names.update(str(k) for k in env)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    for text in workflow_texts.values():
        try:
            walk(yaml.safe_load(text) or {})
        except yaml.YAMLError:
            continue
    return names


def attesting_ci_path(test_file: Path, targets: Dict[str, bool]) -> Optional[bool]:
    """True if *test_file* sits under a CI target whose job installs the dist.

    ``False`` means CI runs it but cannot record; ``None`` means CI does not run
    it at all — the case that is invisible in a green build and the reason
    ``src/atdd/substrate/tests/`` produces nothing despite passing locally.

    A target is matched as a directory prefix OR as the file itself. Both,
    because a pytest argument is a path and CI uses both kinds: #1643 added two
    `coach/commands/tests` FILES by name rather than import that directory's
    debt, and a prefix-only match credited neither — it reported the one form of
    coverage the repository reaches for when a whole directory is too red as no
    coverage at all.
    """
    posix = test_file.as_posix()
    covered = [
        (target, installs)
        for target, installs in targets.items()
        if posix == target.rstrip("/") or posix.startswith(target.rstrip("/") + "/")
    ]
    if not covered:
        return None
    return any(installs for _, installs in covered)


def ci_runner_verdict(
    test_files: "List[Path]",
    targets: Dict[str, bool],
    gated_env: Set[str],
    ci_env: Set[str],
) -> str:
    """How this acceptance's anchored tests fare in CI, as one of four verdicts.

    Written once and here because the census is derived data: #1664 shipped the
    ``ci-runner`` column with no committed function that reproduces it, so the
    only copy of this rule lived in the throwaway script that generated the
    table, and nothing could disagree with it because nothing else computed it.

    ``CI_TEST_OPTS_OUT`` outranks ``CI_RUNS_WITH_HOOK``: a job that installs the
    distribution and then runs a test which deselects itself has not run it, and
    reporting that alongside the jobs that did would be the same shape as the
    green-because-nothing-ran gates this census exists to find.

    None of the four verdicts asserts that evidence was produced. #1815 measured
    that a CI run produces none at all, so this axis reports only what it can
    see: whether the invocation loads the hook and whether the test executes.
    """
    unsatisfied = gated_env - ci_env
    verdicts = [attesting_ci_path(path, targets) for path in test_files]
    if not any(v is not None for v in verdicts):
        return NOT_RUN_BY_CI
    if unsatisfied:
        return CI_TEST_OPTS_OUT
    return CI_RUNS_WITH_HOOK if any(v is True for v in verdicts) else CI_RUNS_WITHOUT_HOOK
