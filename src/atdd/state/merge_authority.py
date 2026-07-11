"""The merge-authority run — CI as the gate, not a signal (#1400 enforce-merge-authority).

Invariant I6: *local hooks are convenience; CI/branch protection is authority.* A hook can
be skipped with ``--no-verify``, a pre-push check runs on the developer's machine against
the developer's store, and neither is a guarantee anyone else can rely on. So every gate a
hook runs must have an equivalent server-side check that runs on push and on pull request,
and **any one of them failing must fail the run** (spec §4).

The seven required checks (spec §4):

===========================  =============================================================
``projection-canonicality``  ``project(hydrate(committed projection)) == committed``.
``projection-schema``        every ``<uid>.yaml`` conforms to ``commons:projection-object``.
``legal-transition``         the load-bearing gate: no canonical-but-illegal lifecycle jump.
``trailer-cross-check``      the git event log matches the projection changes it claims.
``field-writer``             no writer touched a field it does not own.
``no-secrets``               no raw token reaches the immutable history (I8).
``core-no-provider``         core's hot path imports no provider; it runs against bare git.
===========================  =============================================================

The check set is *data* (:data:`REQUIRED_CHECKS`) and each check is a function, so the run
is evaluable without GitHub: a caller can substitute a check to force it to fail and watch
the run fail with it. That is the same property CI relies on and the same one the branch-
protection policy (:mod:`atdd.state.policy`) pins as required contexts.

The whole run reads git and the working tree. It reads no GitHub API and no developer
SQLite store — which is precisely why it is green against a bare git remote.

Dependency discipline: stdlib + ``atdd.state`` only.
"""
from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple

import yaml

from atdd.state import crosscheck, dispositions, evidence, secrets
from atdd.state.projection import (
    PROJECTION_RELATIVE,
    PROJECTION_SUFFIX,
    ProjectionError,
    check_canonicality,
    validate_document,
)
from atdd.state.trailers import NON_PROJECTION, TrailerBlock, TrailerParseError, parse_trailers

_log = logging.getLogger(__name__)

#: The required-check set (spec §4). The order is the order CI reports them in, and the
#: names are the status-check contexts branch protection makes required.
CHECK_CANONICALITY = "projection-canonicality"
CHECK_SCHEMA = "projection-schema"
CHECK_TRANSITION = "legal-transition"
CHECK_TRAILER = "trailer-cross-check"
CHECK_FIELD_WRITER = "field-writer"
CHECK_NO_SECRETS = "no-secrets"
CHECK_NO_PROVIDER = "core-no-provider"

REQUIRED_CHECKS: Tuple[str, ...] = (
    CHECK_CANONICALITY,
    CHECK_SCHEMA,
    CHECK_TRANSITION,
    CHECK_TRAILER,
    CHECK_FIELD_WRITER,
    CHECK_NO_SECRETS,
    CHECK_NO_PROVIDER,
)

#: The modules the merge authority itself runs on. None of them may import a provider —
#: that is what "core runs against a bare git remote" means in code rather than in prose
#: (spec §8.1: *provider code imports core; core never imports provider code*).
HOT_PATH_MODULES: Tuple[str, ...] = (
    "projection", "identity", "overlay", "reconcile", "metadata", "authoring",
    "trailers", "evidence", "crosscheck", "secrets", "merge_authority", "policy",
)

#: An import of any of these from a hot-path module means core has grown a provider
#: dependency. ``atdd.state.providers`` is the *registry*, which is core — but importing
#: it from the lifecycle path would mean a lifecycle decision could consult a provider,
#: and that is the boundary this check exists to hold (I7).
FORBIDDEN_IMPORT_RE = re.compile(
    r"^\s*(?:from|import)\s+(?P<target>"
    r"github|requests|urllib\.request|atdd\.integrations|atdd\.state\.providers"
    r"|atdd\.state\.sync_engine|atdd\.state\.sync_cli)\b",
    re.MULTILINE,
)


class MergeAuthorityError(RuntimeError):
    """The merge-authority run could not be performed (a git or input fault, not a gate)."""


@dataclass(frozen=True)
class CheckResult:
    """One required check's verdict."""

    name: str
    ok: bool
    report: str

    def render(self) -> str:
        mark = "PASS" if self.ok else "FAIL"
        return f"[{mark}] {self.name}\n" + "\n".join(
            f"       {line}" for line in self.report.splitlines()
        )


@dataclass(frozen=True)
class RunResult:
    """The merge-authority run: every check, and the single verdict they add up to."""

    results: List[CheckResult] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        """The run passes only when *every* check passes — no check is advisory (I6)."""
        return all(result.ok for result in self.results)

    @property
    def exit_code(self) -> int:
        return 0 if self.ok else 1

    @property
    def failed(self) -> List[str]:
        return [result.name for result in self.results if not result.ok]

    def result_for(self, name: str) -> Optional[CheckResult]:
        for result in self.results:
            if result.name == name:
                return result
        return None

    def render(self) -> str:
        lines = [result.render() for result in self.results]
        if self.ok:
            lines.append(f"merge-authority run PASSED ({len(self.results)} check(s))")
        else:
            lines.append(
                f"merge-authority run FAILED: {self.failed} "
                f"({len(self.failed)}/{len(self.results)} check(s))"
            )
        return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Git — the only backend the run needs
# --------------------------------------------------------------------------- #
def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=str(repo), capture_output=True, text=True, timeout=120,
    )
    if result.returncode != 0:
        raise MergeAuthorityError(
            f"git {' '.join(args)} failed in {repo}: {result.stderr.strip()}"
        )
    return result.stdout


def projection_at(repo: Path, ref: Optional[str]) -> Dict[str, Dict[str, Any]]:
    """The committed projection at a git ``ref``, keyed by uid (``{}`` for no ref).

    Read out of the git object database, never off the working tree: the merge base is a
    commit, not a checkout, and re-checking it out to read it would be both slow and a
    way to lose the developer's uncommitted work.
    """
    if ref is None:
        return {}
    prefix = PROJECTION_RELATIVE.as_posix()
    listing = _git(repo, "ls-tree", "-r", "--name-only", ref, "--", prefix)
    documents: Dict[str, Dict[str, Any]] = {}
    for path in sorted(line.strip() for line in listing.splitlines() if line.strip()):
        if not path.endswith(PROJECTION_SUFFIX):
            continue
        document = yaml.safe_load(_git(repo, "show", f"{ref}:{path}"))
        if isinstance(document, dict) and document.get("uid"):
            documents[str(document["uid"])] = document
    return documents


def changed_paths(repo: Path, base: Optional[str], head: str = "HEAD") -> List[str]:
    """Every path the range ``base..head`` touched (the whole tree for no base)."""
    if base is None:
        return sorted(
            line.strip() for line in _git(repo, "ls-tree", "-r", "--name-only", head).splitlines()
            if line.strip()
        )
    return sorted(
        line.strip()
        for line in _git(repo, "diff", "--name-only", f"{base}..{head}").splitlines()
        if line.strip()
    )


def commit_message(repo: Path, ref: str = "HEAD") -> str:
    """The full message of a commit — the raw material the trailer parser reads."""
    return _git(repo, "log", "-1", "--format=%B", ref)


def merge_base(repo: Path, base_ref: str, head: str = "HEAD") -> Optional[str]:
    """The merge base of ``base_ref`` and ``head``, or ``None`` when they share no history."""
    try:
        out = _git(repo, "merge-base", base_ref, head).strip()
    except MergeAuthorityError as exc:
        _log.info(
            "no merge base; the diff is taken against the empty projection",
            extra={"base_ref": base_ref, "head": head, "error": str(exc)},
        )
        return None
    return out or None


# --------------------------------------------------------------------------- #
# The run's shared input — resolved once, handed to every check
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Context:
    """Everything the seven checks read, resolved once from git and the working tree."""

    repo: Path
    projection_dir: Path
    base_ref: Optional[str]
    head_ref: str
    base: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    head: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    paths: List[str] = field(default_factory=list)
    message: str = ""
    block: Optional[TrailerBlock] = None
    trailer_error: Optional[str] = None
    actor: str = ""

    @property
    def evidence_by_uid(self) -> Dict[str, Any]:
        """The evidence each changed object's commit actually carries (spec §6)."""
        return {
            uid: evidence.evidence_for(
                document, self.paths,
                None if self.block is None else self.block.group_for(uid),
            )
            for uid, document in self.head.items()
        }

    @property
    def trailer_mapping(self) -> Dict[str, str]:
        """Every ``ATDD-*`` trailer value in the commit, flattened — the secrets surface."""
        mapping: Dict[str, str] = {}
        if self.block is None:
            return mapping
        for index, group in enumerate(self.block.groups):
            for key, value in group.as_mapping().items():
                mapping[key if index == 0 else f"{key}[{index}]"] = value
        if self.block.summary is not None:
            mapping["ATDD-Summary"] = self.block.summary
        if self.block.summary_digest is not None:
            mapping["ATDD-Summary-Digest"] = self.block.summary_digest
        return mapping


def build_context(
    repo: Path,
    *,
    base_ref: Optional[str] = None,
    head_ref: str = "HEAD",
    actor: str = "",
) -> Context:
    """Resolve the run's inputs from git — the merge base, the diff, and the trailers."""
    repo = Path(repo).resolve()
    base_sha = merge_base(repo, base_ref, head_ref) if base_ref else None
    message = commit_message(repo, head_ref)
    block: Optional[TrailerBlock] = None
    trailer_error: Optional[str] = None
    try:
        block = parse_trailers(message)
    except TrailerParseError as exc:
        trailer_error = str(exc)
    return Context(
        repo=repo,
        projection_dir=repo / PROJECTION_RELATIVE,
        base_ref=base_sha,
        head_ref=head_ref,
        base=projection_at(repo, base_sha),
        head=projection_at(repo, head_ref),
        paths=changed_paths(repo, base_sha, head_ref),
        message=message,
        block=block,
        trailer_error=trailer_error,
        actor=actor,
    )


# --------------------------------------------------------------------------- #
# The seven checks
# --------------------------------------------------------------------------- #
def check_canonicality_(context: Context) -> CheckResult:
    try:
        report = check_canonicality(context.projection_dir)
    except ProjectionError as exc:
        _log.warning("canonicality check refused the projection", extra={"error": str(exc)})
        return CheckResult(CHECK_CANONICALITY, False, str(exc))
    return CheckResult(CHECK_CANONICALITY, report.ok, report.render())


def check_schema(context: Context) -> CheckResult:
    problems: List[str] = []
    for uid in sorted(context.head):
        try:
            validate_document(context.head[uid])
        except ProjectionError as exc:
            problems.append(str(exc))
    if problems:
        return CheckResult(CHECK_SCHEMA, False, "\n".join(problems))
    return CheckResult(
        CHECK_SCHEMA, True,
        f"every committed projection object conforms to commons:projection-object "
        f"({len(context.head)} object(s))",
    )


def check_transition(context: Context) -> CheckResult:
    report = evidence.validate_projection_diff(
        context.base, context.head, context.evidence_by_uid,
    )
    return CheckResult(CHECK_TRANSITION, report.ok, report.render())


def check_trailers(context: Context) -> CheckResult:
    if context.trailer_error is not None:
        return CheckResult(CHECK_TRAILER, False, context.trailer_error)
    block = context.block or TrailerBlock(commit_kind=NON_PROJECTION)
    report = crosscheck.cross_check(block, context.base, context.head, repo_root=context.repo)
    return CheckResult(CHECK_TRAILER, report.ok, report.render())


def check_field_writer(context: Context) -> CheckResult:
    report = crosscheck.check_field_ownership(context.base, context.head, actor=context.actor)
    return CheckResult(CHECK_FIELD_WRITER, report.ok, report.render())


def check_no_secrets(context: Context) -> CheckResult:
    report = secrets.scan(trailers=context.trailer_mapping, documents=context.head)
    return CheckResult(CHECK_NO_SECRETS, report.ok, report.render())


def hot_path_provider_imports() -> List[str]:
    """Every hot-path module that imports a provider — empty is the invariant (spec §8.1)."""
    here = Path(__file__).resolve().parent
    offenders: List[str] = []
    for name in HOT_PATH_MODULES:
        path = here / f"{name}.py"
        if not path.is_file():
            continue
        for match in FORBIDDEN_IMPORT_RE.finditer(path.read_text(encoding="utf-8")):
            offenders.append(f"{name}.py imports {match.group('target')}")
    return sorted(offenders)


def check_no_provider(context: Context) -> CheckResult:
    offenders = hot_path_provider_imports()
    if offenders:
        return CheckResult(CHECK_NO_PROVIDER, False, "\n".join(offenders))
    return CheckResult(
        CHECK_NO_PROVIDER, True,
        f"core's lifecycle path imports no provider ({len(HOT_PATH_MODULES)} module(s)); "
        "the run is satisfiable by git alone",
    )


#: The default check implementations. A caller may substitute any one of them — that is
#: how the run is evaluated with a check forced to fail (E002).
DEFAULT_CHECKS: Dict[str, Callable[[Context], CheckResult]] = {
    CHECK_CANONICALITY: check_canonicality_,
    CHECK_SCHEMA: check_schema,
    CHECK_TRANSITION: check_transition,
    CHECK_TRAILER: check_trailers,
    CHECK_FIELD_WRITER: check_field_writer,
    CHECK_NO_SECRETS: check_no_secrets,
    CHECK_NO_PROVIDER: check_no_provider,
}


def run(
    context: Context,
    *,
    checks: Optional[Mapping[str, Callable[[Context], CheckResult]]] = None,
    only: Optional[Sequence[str]] = None,
) -> RunResult:
    """Execute the required-check set; the run fails if *any* check fails (E002).

    No check is advisory and none is skipped on failure — a run that reported six passes
    and shrugged at the seventh would be exactly the "advisory signal" I6 forbids.
    """
    table = dict(DEFAULT_CHECKS)
    table.update(checks or {})
    names = list(only or REQUIRED_CHECKS)
    unknown = [name for name in names if name not in table]
    if unknown:
        raise MergeAuthorityError(f"unknown check(s): {unknown}; the set is {list(REQUIRED_CHECKS)}")
    results = [table[name](context) for name in names]
    result = RunResult(results=results)
    if not result.ok:
        _log.warning("merge-authority run failed", extra={"failed": result.failed})
    return result


def run_repo(
    repo: Path,
    *,
    base_ref: Optional[str] = None,
    head_ref: str = "HEAD",
    actor: str = "",
    checks: Optional[Mapping[str, Callable[[Context], CheckResult]]] = None,
    only: Optional[Sequence[str]] = None,
) -> RunResult:
    """Build the context from ``repo`` and run the required-check set over it."""
    context = build_context(repo, base_ref=base_ref, head_ref=head_ref, actor=actor)
    return run(context, checks=checks, only=only)


def disposition_report(repo: Path) -> dispositions.DispositionReport:
    """The convention-disposition check (C004) — a repository gate, not a diff gate."""
    return dispositions.scan_conventions(Path(repo))
