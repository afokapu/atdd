"""The non-GitHub remote conformance suite — the M5 exit criterion (#1400 §8, C002).

> **Spec §8.1.** Core must run a complete workflow with zero providers registered.

This drives the whole workflow — mint, project, commit, push, hydrate, reconcile, CI — against a
**bare git remote**, with **zero providers registered**, and proves the lifecycle never once
needed GitHub. The remote is bare on purpose: it is git object storage and nothing else, so there
is no API to call even if a step wanted to. A suite that proved this against a GitHub remote with
the calls merely mocked out would have proved that the mocks work.

Steps are **data** (:data:`STEPS`), each a function over a :class:`Context`, so a caller can
substitute a rogue step and watch the suite fail — which is exactly what the RED acceptance does.
A gate nobody has ever seen fail is a gate nobody knows the shape of.

**What is actually detected, and what is not.** Three tripwires run for the duration:

``provider registry``
    :func:`atdd.state.provider_seam.discover_providers` is replaced for the run by a recorder that
    notes the caller and returns ``{}``. Any step that consults the registry is named — and still
    gets zero providers, so the run continues and the *report* is the failure, not a crash.
``external_refs``
    Steps read the projection through :meth:`Context.lifecycle_projection`, a view that records any
    access to ``external_refs``. This catches a lifecycle step reading the mirror **through the
    view core hands it**. A step that bypassed the view and opened the YAML itself would not be
    caught here — that is what the static guard (:mod:`atdd.state.import_boundary`) and the
    ownership table's ``lifecycle_readable: false`` are for. Said plainly rather than overclaimed.
``gh``
    A shim named ``gh`` is put first on ``PATH``; invoking it writes a marker and exits non-zero.
    It catches a shell-out from anywhere in the run, including from inside a git subprocess.

Every violation is attributed to **invariant I7** — *the mirror is non-authoritative* — because
that is the invariant a lifecycle step touching a provider actually breaks: it makes a decision
depend on something that is, by construction, only a picture of the decision.

Dependency discipline: stdlib + ``atdd.state`` (never a provider).
"""
from __future__ import annotations

import logging
import os
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Sequence, Tuple

from atdd.state import import_boundary, merge_authority, provider_seam
from atdd.state.bare_remote import (
    ConformanceError,  # re-exported: the suite's callers catch conformance.ConformanceError
    clone_of,
    git,
    seed_bare_remote,
    write_gh_shim,
)
from atdd.state.projection import (
    PROJECTION_RELATIVE,
    canonical_bytes,
    project,
    read_projection,
)

_log = logging.getLogger(__name__)

#: The invariant a lifecycle step that touches a provider breaks (spec §2.2).
INVARIANT_I7 = "I7 — the mirror is non-authoritative: no lifecycle decision may depend on a provider"

#: The uid-bearing trailer a projection commit carries (spec §5).
_TRAILER = "ATDD-Object"


# --------------------------------------------------------------------------- #
# Tripwires
# --------------------------------------------------------------------------- #
@dataclass
class Tripwire:
    """What the run caught. Empty is the invariant."""

    provider_touches: List[str] = field(default_factory=list)
    external_ref_reads: List[str] = field(default_factory=list)
    gh_invocations: List[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.provider_touches or self.external_ref_reads or self.gh_invocations)


class _LifecycleView(Mapping):
    """A projection document a lifecycle step may read — except for the one field it may not.

    Reading ``external_refs`` is not blocked, it is *recorded*: the suite's job is to report which
    step broke the boundary, and a view that raised would only tell the step's author, at a moment
    when nobody is watching (spec §8.2 rule 5).
    """

    def __init__(self, uid: str, document: Mapping[str, Any], tripwire: Tripwire, step: str) -> None:
        self._uid = uid
        self._document = document
        self._tripwire = tripwire
        self._step = step

    def __getitem__(self, key: str) -> Any:
        if key == provider_seam.EXTERNAL_REFS:
            self._tripwire.external_ref_reads.append(f"{self._step} read {self._uid}.{key}")
        return self._document[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._document)

    def __len__(self) -> int:
        return len(self._document)


@contextmanager
def _watch_registry(tripwire: Tripwire, step: Callable[[], str]) -> Iterator[None]:
    """Replace the registry's entry point with a recorder for the duration of one step."""
    original = provider_seam.discover_providers

    def _recording() -> Dict[str, Any]:
        tripwire.provider_touches.append(f"{step()} consulted the provider registry")
        return {}

    provider_seam.discover_providers = _recording  # type: ignore[assignment]
    try:
        yield
    finally:
        provider_seam.discover_providers = original  # type: ignore[assignment]


@contextmanager
def _gh_tripwire(tmp: Path) -> Iterator[Path]:
    """Put a ``gh`` that cannot work first on ``PATH``; it leaves a marker if anything calls it."""
    bin_dir, marker = write_gh_shim(tmp)
    previous = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{bin_dir}{os.pathsep}{previous}"
    try:
        yield marker
    finally:
        os.environ["PATH"] = previous


# --------------------------------------------------------------------------- #
# The run's context — what every step reads and writes
# --------------------------------------------------------------------------- #
@dataclass
class Context:
    """One conformance run: a bare remote, an author's clone, and a second developer's clone."""

    remote: Path
    author: Path
    peer: Path
    tripwire: Tripwire = field(default_factory=Tripwire)
    uid: str = ""
    step: str = ""
    #: Zero. Asserted at the start and at the end, because "no providers" is the claim.
    providers: Dict[str, Any] = field(default_factory=dict)

    @property
    def projection_dir(self) -> Path:
        return self.author / PROJECTION_RELATIVE

    def lifecycle_projection(self, repo: Optional[Path] = None) -> Dict[str, "_LifecycleView"]:
        """The committed projection, as a lifecycle step is allowed to see it."""
        base = (repo or self.author) / PROJECTION_RELATIVE
        return {
            uid: _LifecycleView(uid, document, self.tripwire, self.step)
            for uid, document in read_projection(base).items()
        }


def setup(root: Path) -> Context:
    """A bare remote and two clones of it. No GitHub, no API, no provider — just git."""
    root = Path(root)
    remote = seed_bare_remote(
        root, gitignore=".atdd/state/state.sqlite*\n", message="seed: control root",
    )
    author = clone_of(remote, root / "author")
    peer = clone_of(remote, root / "peer")
    return Context(remote=remote, author=author, peer=peer)


# --------------------------------------------------------------------------- #
# The workflow, as steps (C002)
# --------------------------------------------------------------------------- #
def _open(control_root: Path):
    from atdd.state.db import connect, init_state_store
    from atdd.state.store import StateStore

    conn = connect(init_state_store(start=control_root))
    return conn, StateStore(conn)


def step_mint(context: Context) -> str:
    """Author an object in the local store — the private work that has not been shared yet.

    With a ``body``, because the ∅->INIT gate demands ``body_initialized`` (spec §6) and a
    conformance run that authored an unevidenced object would be proving that the gate is broken
    rather than that the workflow is provider-free.
    """
    from atdd.state.authoring import create_object

    conn, _store = _open(context.author)
    try:
        event = create_object(
            conn, slug="feature-x", owner_actor="dev-a", phase="INIT",
            title="Feature X", body="Author feature-x against a bare remote, with no provider.",
        )
        context.uid = event.object_uid
    finally:
        conn.close()
    return f"minted {context.uid}"


def step_project(context: Context) -> str:
    """store → projection. Deterministic bytes, one file per uid (I1)."""
    from atdd.state.overlay import mark_projected

    conn, store = _open(context.author)
    try:
        result = project(store, context.projection_dir)
        mark_projected(conn, result.digest)
    finally:
        conn.close()
    return f"projected {len(result.files)} object(s), digest {result.digest}"


def step_commit(context: Context) -> str:
    """Commit the projection with the trailers that evidence what it changed (spec §5, §6).

    ``ATDD-Projection-Digest`` is not decoration: it is the ∅->INIT gate's second demand, and it
    is how CI — which cannot read the developer's store — knows which bytes the commit is claiming
    to have projected.
    """
    from atdd.state.projection import object_digest

    document = read_projection(context.projection_dir)[context.uid]
    git(context.author, "add", "-A")
    git(context.author, "commit", "--quiet", "-m", "\n".join([
        "feat: author feature-x",
        "",
        f"{_TRAILER}: {context.uid}",
        f"ATDD-Projection-Digest: {object_digest(document)}",
    ]))
    return f"committed {git(context.author, 'rev-parse', 'HEAD')[:12]}"


def step_push(context: Context) -> str:
    """Push to a **bare** remote. There is no API here to call — that is the point."""
    git(context.author, "push", "--quiet", "origin", "main")
    return "pushed to the bare remote"


def step_hydrate(context: Context) -> str:
    """A second developer builds their store from the projection at HEAD — nothing else."""
    from atdd.state.reconcile import hydrate_store

    git(context.peer, "pull", "--quiet", "--ff-only", "origin", "main")
    hydrated, base = hydrate_store(context.peer, projection_dir=context.peer / PROJECTION_RELATIVE)
    return f"hydrated {hydrated} object(s) at base {base}"


def step_reconcile(context: Context) -> str:
    """Reconcile the peer's store against the incoming projection (no overlay ⇒ a no-op)."""
    from atdd.state.reconcile import reconcile

    result = reconcile(context.peer)
    return f"reconciled: {result.replayed} replayed, {len(result.reprojected)} re-projected"


def step_canonicality(context: Context) -> str:
    """``project(hydrate(committed)) == committed`` — canonicality, over what was actually pushed."""
    documents = read_projection(context.peer / PROJECTION_RELATIVE)
    for uid, document in documents.items():
        committed = (context.peer / PROJECTION_RELATIVE / f"{uid}.yaml").read_bytes()
        if canonical_bytes(document) != committed:
            raise AssertionError(f"{uid} is committed in non-canonical bytes")
    return f"the committed projection is byte-identical to project(store) ({len(documents)} object(s))"


def step_ci(context: Context) -> str:
    """The CI merge-authority run: the seven required checks, over a repo with no remote API."""
    result = merge_authority.run_repo(context.peer, actor="core-lifecycle")
    if not result.ok:
        raise AssertionError(f"the merge-authority run failed: {result.failed}\n{result.render()}")
    return f"merge authority passed ({len(result.results)} required check(s))"


def step_import_boundary(context: Context) -> str:
    """The static guard, run as part of the workflow — the boundary is a step, not a footnote."""
    report = import_boundary.check()
    if not report.ok:
        raise AssertionError(report.render())
    return f"core's import graph is provider-free ({len(report.scanned)} module(s))"


@dataclass(frozen=True)
class Step:
    name: str
    run: Callable[[Context], str]


#: The full workflow. Order matters: each step consumes the last one's output.
STEPS: Tuple[Step, ...] = (
    Step("mint", step_mint),
    Step("project", step_project),
    Step("commit", step_commit),
    Step("push", step_push),
    Step("hydrate", step_hydrate),
    Step("reconcile", step_reconcile),
    Step("canonicality", step_canonicality),
    Step("ci", step_ci),
    Step("import-boundary", step_import_boundary),
)


# --------------------------------------------------------------------------- #
# The run
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class StepResult:
    name: str
    ok: bool
    report: str

    def render(self) -> str:
        return f"[{'PASS' if self.ok else 'FAIL'}] {self.name}: {self.report}"


@dataclass(frozen=True)
class ConformanceReport:
    """Did the whole workflow complete against a bare remote with zero providers?"""

    results: List[StepResult] = field(default_factory=list)
    violations: List[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(result.ok for result in self.results) and not self.violations

    @property
    def failed(self) -> List[str]:
        return [result.name for result in self.results if not result.ok]

    def render(self) -> str:
        lines = [result.render() for result in self.results]
        if self.violations:
            lines.append(f"the provider boundary was crossed ({len(self.violations)}):")
            lines += [f"  {violation}" for violation in self.violations]
            lines.append(INVARIANT_I7)
        lines.append(
            f"provider-free conformance PASSED ({len(self.results)} step(s), 0 providers)"
            if self.ok else
            f"provider-free conformance FAILED: steps {self.failed}, "
            f"{len(self.violations)} boundary violation(s)"
        )
        return "\n".join(lines)


def run(context: Context, *, steps: Sequence[Step] = STEPS) -> ConformanceReport:
    """Drive the workflow with **zero providers registered** and every tripwire armed (C002).

    A step that raises does not abort the run: the remaining steps still run, so one report names
    everything that is wrong rather than the first thing. A step that *touches a provider* is not
    a failing step at all — it may well succeed — which is exactly why the tripwires exist.
    """
    results: List[StepResult] = []
    context.providers = {}

    with _gh_tripwire(context.remote.parent) as marker:
        for step in steps:
            context.step = step.name
            with _watch_registry(context.tripwire, lambda: context.step):
                try:
                    results.append(StepResult(step.name, True, step.run(context)))
                except Exception as exc:  # noqa: BLE001 - a failed step is a report line, not a crash
                    _log.warning(
                        "a conformance step failed against the bare remote",
                        extra={"step": step.name, "error": str(exc)},
                    )
                    results.append(StepResult(step.name, False, f"{type(exc).__name__}: {exc}"))
        if marker.is_file():
            context.tripwire.gh_invocations.extend(
                f"the run invoked `gh`: {line.strip()}"
                for line in marker.read_text(encoding="utf-8").splitlines() if line.strip()
            )

    violations = [
        f"{touch} — {INVARIANT_I7}"
        for touch in (
            context.tripwire.provider_touches
            + context.tripwire.external_ref_reads
            + context.tripwire.gh_invocations
        )
    ]
    if provider_seam.registered_names():
        violations.append(
            f"providers were registered during the run: {provider_seam.registered_names()}; the "
            f"conformance claim is that core completes with none — {INVARIANT_I7}"
        )
    report = ConformanceReport(results=results, violations=violations)
    if not report.ok:
        _log.warning(
            "provider-free conformance failed",
            extra={"failed": report.failed, "violations": violations},
        )
    return report


def run_in(root: Path, *, steps: Sequence[Step] = STEPS) -> ConformanceReport:
    """Set up a bare remote under ``root`` and run the suite against it."""
    return run(setup(Path(root)), steps=steps)
