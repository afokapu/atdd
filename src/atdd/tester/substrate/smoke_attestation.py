# URN: component:govern-lifecycle:enforcement-substrate:smoke-attestation:backend:integration
# Runtime: python
# Purpose: Pytest hook that records, into the State Store, the fact that an execution_kind: live_smoke acceptance's test actually executed (#1602).

"""The smoke-execution attestation writer (issue #1602).

**This hook is the only producer of smoke-execution evidence in the tree, and
that is the design.** Everything the repo previously called smoke evidence was
producible without running a test:

* ``tester.acceptance-violation.live-smoke-acceptance-must-execute`` (#1151) is a
  static source scan. It proves a live_smoke test *cannot skip itself*. It cannot
  prove it *ran* — nobody ever invoked it.
* ``.atdd/smoke-evidence/<N>.yaml`` (the #358 presentation ratchet) is written by
  ``atdd validate coder --smoke-required``, a command that runs no test. The file
  is indistinguishable between "smoke ran against real infrastructure" and "an
  operator typed a command".

So the attestation is captured where the fact actually exists — inside the pytest
run, from the report of the test itself — and written to the State Store keyed by
work-item uid. There is deliberately **no CLI verb** that writes one. If you can
type it, it is not an attestation.

WHAT IS RECORDED. Every test anchored to an ``execution_kind: live_smoke``
acceptance, with its outcome — including ``skipped``. A skip must be *visible as
a skip*, not absent: #1076 (C010-SMOKE-001) "passed" by skipping, and an absent
record is indistinguishable from a run that never happened. The verdict in
:func:`atdd.state.smoke_evidence.evaluate_smoke_execution` then rejects skips; this
module's job is to tell the truth, not to judge it.

FAILURE POSTURE. A pytest hook must never break the run it observes, so every
fault here is logged and swallowed. That is safe precisely because the consumer
fails closed: a swallowed write means no attestation, and no attestation means
the ``SMOKE->REFACTOR`` gate blocks. Silence here can only ever be stricter,
never laxer.

REGISTRATION. Attached by :mod:`atdd.tester.substrate.plugin`'s
``pytest_configure`` rather than by its own ``pytest11`` entry point, so it needs
no reinstall to take effect — and, unlike the plugin's own collection hook,
it is NOT gated on ``repo.substrate.enabled``. That gate exists to make the
substrate a no-op in consumer repos that never opted in; the lifecycle gate this
attestation feeds is core, and the toolkit repo itself declares no ``repo:``
block, so gating it there would make the toolkit unable to dogfood its own gate.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Set

import pytest

_logger = logging.getLogger(__name__)

#: ``acceptances[].execution_kind`` this hook attests for. Same constant the
#: #1151 self-skip validator selects on — the two must agree about which
#: acceptances are live smoke, or one will police tests the other never records.
LIVE_SMOKE_KIND = "live_smoke"

_GIT_TIMEOUT_S = 10


# --------------------------------------------------------------------------- #
# Git facts about the code under test                                          #
# --------------------------------------------------------------------------- #
def _git(repo_root: Path, *args: str) -> Optional[str]:
    """Run a read-only git command, returning stripped stdout or ``None``.

    Local rather than borrowed from ``atdd.coach.utils.git``: the helpers there
    are private to the manifest-commit flow, and a test-time observer must not
    reach into another module's privates for three one-line reads.
    """
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=_GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.SubprocessError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        _logger.debug(
            "smoke attestation: git %s failed: %s", args, exc,
            extra={"args": list(args), "error_type": type(exc).__name__},
        )
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def _current_branch(repo_root: Path) -> Optional[str]:
    return _git(repo_root, "symbolic-ref", "--short", "HEAD")


def _head_sha(repo_root: Path) -> Optional[str]:
    return _git(repo_root, "rev-parse", "HEAD")


def _is_dirty(repo_root: Path) -> bool:
    """True when tracked files differ from HEAD.

    Recorded, never gated on. A dirty tree is the *normal* state while smoking a
    change, so refusing it would make the gate unusable; but an attestation that
    quietly implied the committed tree was what ran would be the same kind of lie
    this whole issue exists to remove. So it is written down.
    """
    status = _git(repo_root, "status", "--porcelain", "--untracked-files=no")
    return bool(status)


# --------------------------------------------------------------------------- #
# Work-item resolution                                                         #
# --------------------------------------------------------------------------- #
def resolve_work_item_uid(repo_root: Path, store) -> Optional[str]:
    """The work-item uid the current branch is bound to, or ``None``.

    A branch is ``<prefix>/<slug>`` — the same derivation
    ``IssueManager.branch_is_registered`` uses for the pre-commit hook — and the
    slug is then resolved to the object's **minted uid**, which is what the
    attestation must be recorded under. Returning the slug would name no row:
    ``events.object_uid`` is a foreign key onto ``objects(uid)``, so the
    attestation would be refused outright (#1622).

    Resolving from the BRANCH rather than from an issue number is deliberate: a
    pytest run knows what checkout it is in and nothing about GitHub, and
    ``atdd.state.smoke_evidence`` may not consult ``external_refs`` for a lifecycle
    decision (I7). The gate on the other side does the issue-number → uid
    translation itself, one layer up.
    """
    branch = _current_branch(repo_root)
    if not branch:
        return None
    slug = branch.split("/", 1)[-1] if "/" in branch else branch
    try:
        # No issue number is passed, so the resolver never touches external_refs — the
        # I7 quarantine above holds. It resolves the slug through the object's own data.
        from atdd.state.work_item_writer import resolve_work_item

        obj = resolve_work_item(store, slug)
    except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
        _logger.debug(
            "smoke attestation: store lookup for %r failed: %s", slug, exc,
            extra={"slug": slug, "error_type": type(exc).__name__},
        )
        return None
    return obj.uid if obj is not None else None


# --------------------------------------------------------------------------- #
# live_smoke discovery                                                         #
# --------------------------------------------------------------------------- #
#: Cheap pre-filter for :func:`live_smoke_test_files`. Anchored to line start so
#: it matches an actual YAML key and not the many convention/WMBT files whose
#: *prose* discusses ``execution_kind: live_smoke`` inside a quoted scalar.
_LIVE_SMOKE_DECLARATION_RE = re.compile(
    rb"^[ \t-]*execution_kind:[ \t]*[\"']?" + LIVE_SMOKE_KIND.encode(), re.M
)


def _file_declares_live_smoke(path: Path) -> bool:
    """True when ``path``'s bytes carry a ``execution_kind: live_smoke`` YAML key."""
    try:
        blob = path.read_bytes()
    except OSError as exc:
        _logger.debug(
            "plan file unreadable; it declares nothing for this scan",
            extra={"path": str(path), "error": str(exc)},
        )
        return False
    return bool(_LIVE_SMOKE_DECLARATION_RE.search(blob))


def plan_declares_live_smoke(repo_root: Path) -> bool:
    """Fast byte-level answer to "could ``plan/`` hold a live_smoke acceptance?".

    This hook runs on EVERY pytest invocation in the repo, and the authoritative
    walk (``iter_repo_acceptances``, which YAML-parses ~1100 acceptances) costs
    ~0.6s — a tax on every test run, including each of the many the pre-commit
    hook spawns. Scanning ``plan/`` for the literal declaration costs ~0.1s and
    answers "no" for the overwhelmingly common case.

    Conservative in the safe direction: a false positive only spends the full
    walk, which then answers correctly. A false negative is impossible for a
    declaration written as YAML, because that is the shape this matches.
    """
    plan_dir = repo_root / "plan"
    if not plan_dir.is_dir():
        return False
    for dirpath, _dirnames, filenames in os.walk(plan_dir):
        for name in filenames:
            if name.endswith((".yaml", ".yml")) and _file_declares_live_smoke(
                Path(dirpath) / name
            ):
                return True
    return False


def live_smoke_test_files(repo_root: Path) -> Dict[Path, str]:
    """``{anchored_test_file: acceptance_urn}`` for every live_smoke acceptance.

    Built from the same two public walkers the #1151 validator uses
    (``iter_repo_acceptances`` + ``scan_test_acceptance_headers``), so "which
    tests belong to a live_smoke acceptance" has exactly one answer in the repo:
    a test this hook attests for is exactly a test that validator polices.
    """
    if not plan_declares_live_smoke(repo_root):
        return {}

    from atdd.tester.validators._acceptance_walker import (
        acceptance_urn,
        iter_repo_acceptances,
        scan_test_acceptance_headers,
    )

    urns: Set[str] = set()
    for raw in iter_repo_acceptances(repo_root):
        if raw.body.get("execution_kind") != LIVE_SMOKE_KIND:
            continue
        urn = acceptance_urn(raw.body)
        if urn:
            urns.add(urn)
    if not urns:
        return {}

    index = scan_test_acceptance_headers(repo_root)
    anchored: Dict[Path, str] = {}
    for urn in sorted(urns):
        for path in index.get(urn, []):
            anchored[path.resolve()] = urn
    return anchored


# --------------------------------------------------------------------------- #
# The plugin                                                                   #
# --------------------------------------------------------------------------- #
class SmokeAttestationPlugin:
    """Pytest plugin object carrying the session's attestation state.

    An instance rather than the module, because the state (which files are
    live_smoke, what ran) belongs to one session and ``pytest_runtest_logreport``
    is handed only a report — it has no session to hang state off. Registered by
    :func:`atdd.tester.substrate.plugin.pytest_configure`.
    """

    def __init__(self) -> None:
        self.repo_root: Optional[Path] = None
        #: acceptance URN per anchored test file (absolute, resolved).
        self.acceptance_by_file: Dict[Path, str] = {}
        #: Buffered runs, flushed to the store once at session end.
        self.pending: List[Dict[str, object]] = []

    # -- collection --------------------------------------------------------- #
    def pytest_collection_modifyitems(
        self, session: pytest.Session, config: pytest.Config, items: List[pytest.Item]
    ) -> None:
        """Resolve, once, which collected tests this session must attest for."""
        if not items:
            return
        try:
            repo_root = _repo_root_for(config)
            if repo_root is None:
                return
            anchored = live_smoke_test_files(repo_root)
            if not anchored:
                return  # nothing in plan/ claims live smoke — the hook is a no-op
            self.repo_root = repo_root
            self.acceptance_by_file = anchored
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
            # Never break collection. Nothing recorded => the gate blocks.
            # Silence here is strictly stricter, never laxer.
            _logger.warning(
                "smoke attestation: discovery failed, nothing will be attested: %s", exc,
                extra={"error_type": type(exc).__name__},
            )

    # -- per-test outcome --------------------------------------------------- #
    def pytest_runtest_logreport(self, report) -> None:
        """Buffer one run record per live_smoke test, whatever its outcome.

        Which reports count is :func:`_carries_an_outcome`; listening to only one
        pytest phase would make a whole class of non-execution invisible — the
        #1076 bug restated.
        """
        if not self.acceptance_by_file or not _carries_an_outcome(report):
            return

        path = _report_path(report, self.repo_root)
        if path is None or path not in self.acceptance_by_file:
            return

        outcome = _report_outcome(report)
        self.pending.append({
            "nodeid": report.nodeid,
            "outcome": outcome,
            "duration_s": float(getattr(report, "duration", 0.0) or 0.0),
            "acceptance_urn": self.acceptance_by_file.get(path),
        })

    # -- flush -------------------------------------------------------------- #
    def pytest_sessionfinish(self, session: pytest.Session, exitstatus: int) -> None:
        """Write the buffered runs to the State Store, over one connection."""
        if not self.pending or self.repo_root is None:
            return
        try:
            self._flush()
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow)
            _logger.warning(
                "smoke attestation: could not record %d run(s); the SMOKE->REFACTOR "
                "gate will read this as 'smoke did not run': %s",
                len(self.pending), exc,
                extra={"error_type": type(exc).__name__, "runs": len(self.pending)},
            )
        finally:
            self.pending.clear()

    def _flush(self) -> None:
        from atdd.state.smoke_evidence import SmokeRun, open_state_store, record_smoke_execution

        repo_root = self.repo_root
        assert repo_root is not None  # guarded by the caller
        head = _head_sha(repo_root)
        dirty = _is_dirty(repo_root)

        with open_state_store(control_root=repo_root) as store:
            uid = resolve_work_item_uid(repo_root, store)
            if uid is None:
                _logger.warning(
                    "smoke attestation: this branch resolves to no registered work "
                    "item; %d live-smoke run(s) go unrecorded",
                    len(self.pending), extra={"runs": len(self.pending)},
                )
                return
            for entry in self.pending:
                record_smoke_execution(store, uid, SmokeRun(
                    nodeid=str(entry["nodeid"]),
                    outcome=str(entry["outcome"]),
                    duration_s=float(entry["duration_s"]),
                    commit_sha=head,
                    dirty=dirty,
                    execution_kind=LIVE_SMOKE_KIND,
                    acceptance_urn=entry.get("acceptance_urn"),  # type: ignore[arg-type]
                ))
            _logger.info(
                "smoke attestation: recorded %d live-smoke run(s) for %s",
                len(self.pending), uid, extra={"uid": uid, "runs": len(self.pending)},
            )


# --------------------------------------------------------------------------- #
# Helpers                                                                      #
# --------------------------------------------------------------------------- #
def _repo_root_for(config: pytest.Config) -> Optional[Path]:
    from atdd.coach.utils.repo import find_repo_root

    rootpath = getattr(config, "rootpath", None)
    candidates = [Path(rootpath)] if rootpath is not None else []
    candidates.append(Path.cwd())
    for candidate in candidates:
        try:
            return find_repo_root(candidate.resolve())
        except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow)
            continue
    return None


def _carries_an_outcome(report) -> bool:
    """True when this report states how a test ended.

    Both phases are consulted because a skip and a pass arrive differently: a
    ``@pytest.mark.skip``/fixture skip is reported at ``setup`` and never reaches
    ``call``, while a pass, a failure, or an in-body ``pytest.skip()`` is reported
    at ``call``. A *successful* setup is not an outcome — wait for ``call``.
    """
    if report.when not in ("setup", "call"):
        return False
    return report.when != "setup" or bool(report.skipped)


def _report_outcome(report) -> str:
    """``skipped`` / ``passed`` / ``failed`` for one report."""
    if report.skipped:
        return "skipped"
    return "passed" if report.passed else "failed"


def _report_path(report, repo_root: Optional[Path]) -> Optional[Path]:
    """Absolute path of the test file a report belongs to.

    ``TestReport`` carries only ``location[0]`` / ``fspath``, which pytest
    renders RELATIVE to the rootdir; resolving it against ``repo_root`` (and
    falling back to cwd) is what turns it back into the absolute path the
    acceptance index is keyed by.
    """
    raw = getattr(report, "fspath", None) or (report.location[0] if report.location else None)
    if not raw:
        return None
    candidate = Path(str(raw))
    try:
        if candidate.is_absolute():
            return candidate.resolve()
        for base in (repo_root, Path.cwd()):
            if base is None:
                continue
            resolved = (base / candidate).resolve()
            if resolved.exists():
                return resolved
        return candidate.resolve()
    except OSError as exc:
        _logger.debug(
            "report path did not resolve; the report attests for no test file",
            extra={"raw": str(raw), "repo_root": str(repo_root), "error": str(exc)},
        )
        return None


__all__ = [
    "LIVE_SMOKE_KIND",
    "SmokeAttestationPlugin",
    "live_smoke_test_files",
    "resolve_work_item_uid",
]
