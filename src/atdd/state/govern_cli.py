"""``atdd state`` field-governance verbs (#1400 govern-projection-fields).

The operator- and CI-facing surface over the ownership spine:

- ``atdd state ownership-check`` — every projection field resolves to one declared writer
  and one merge rule, or the policy is refused naming the gap (C001, D001).
- ``atdd state field-writer [--base REF] [--actor A]`` — refuse a projection diff whose
  committing actor does not own a field it touched, in both directions: a human writing
  ``external_refs``, an extension bot writing a lifecycle field (E001).
- ``atdd state merge-projection --base %O --ours %A --theirs %B`` — git's merge driver for
  ``.atdd/state/projection/*.yaml``. Exit ``0`` merged (the result is written over ``%A`` in
  canonical bytes), non-zero conflicted with a report naming the field, both writers and the
  failing rule — and **nothing written** (E002, R001, K001).
- ``atdd state merge-matrix-check`` — every declared merge rule is exercised against every
  divergence case (C002).
- ``atdd state compact-archive`` — the one operation that physically removes a tombstoned
  projection file. Nothing on the merge path can reach it (K001).

Register the driver in a checkout with::

    git config merge.atdd-projection.name "ATDD projection merge driver"
    git config merge.atdd-projection.driver "atdd state merge-projection --base %O --ours %A --theirs %B"
    echo '.atdd/state/projection/*.yaml merge=atdd-projection' >> .gitattributes

Exit codes are the contract git and CI rely on: ``0`` admitted, ``1`` refused. A refusal is
printed to **stderr** so it survives a driver invocation whose stdout git does not show.

Dependency discipline: stdlib + ``pyyaml`` + ``atdd.state`` only. No provider, no network.
"""
from __future__ import annotations

import logging
import os
import re
import sys
from pathlib import Path
from typing import Iterable, List, Optional

import yaml

from atdd.state import merge_driver, merge_matrix, ownership, tombstone
from atdd.state.merge_driver import EVIDENCE_RELATIVE, MergeDriverError
from atdd.state.ownership import OwnershipError, PolicyNotFound

_log = logging.getLogger(__name__)

#: The ``atdd state`` sub-commands this module owns.
OPS = (
    "ownership-check", "field-writer", "merge-projection", "merge-matrix-check",
    "compact-archive",
)


def add_parsers(sub) -> None:
    """Register the field-governance verbs on the ``atdd state`` sub-parser."""
    own = sub.add_parser(
        "ownership-check",
        help="Prove every projection field resolves to one declared writer and merge rule.")
    own.add_argument("--policy", default=None, help="Policy file (default: the committed one).")
    own.add_argument("--root", default=None, help="Repository root (default: cwd).")

    fw = sub.add_parser(
        "field-writer",
        help="CI gate: refuse a projection diff whose writer does not own a field it touched.")
    fw.add_argument("--base", default=None, help="Base ref the diff is taken against.")
    fw.add_argument("--head", default="HEAD", help="Head ref (default: HEAD).")
    fw.add_argument("--actor", default=None,
                    help="The committing actor (default: the head commit's git author).")
    fw.add_argument("--root", default=None, help="Repository root (default: cwd).")

    md = sub.add_parser(
        "merge-projection",
        help="git merge driver for the per-uid projection: safe merges only, conflicts by design.")
    md.add_argument("--base", default=None, help="The merge base of the file (git's %%O).")
    md.add_argument("--ours", required=True, help="Our version (git's %%A; the result is written here).")
    md.add_argument("--theirs", required=True, help="Their version (git's %%B).")
    md.add_argument("--output", default=None, help="Write the merged object here instead of --ours.")
    md.add_argument("--ours-evidence", default=None,
                    help="Comma-separated evidence tokens our side carries (default: from git).")
    md.add_argument("--theirs-evidence", default=None,
                    help="Comma-separated evidence tokens their side carries (default: from git).")
    md.add_argument("--root", default=None, help="Repository root (default: cwd).")

    mm = sub.add_parser(
        "merge-matrix-check",
        help="Prove every declared merge rule is exercised against every divergence case.")
    mm.add_argument("--root", default=None, help="Repository root (default: cwd).")

    ca = sub.add_parser(
        "compact-archive",
        help="Archival: physically remove TOMBSTONED projection files (the only deletion path).")
    ca.add_argument("--uid", action="append", default=None,
                    help="Restrict to these uids (repeatable; default: every tombstoned object).")
    ca.add_argument("--from", dest="from_dir", default=None, help="Projection directory.")
    ca.add_argument("--root", default=None, help="Repository root (default: cwd).")


def _root(args) -> Path:
    return Path(getattr(args, "root", None) or Path.cwd()).resolve()


def _policy(args) -> ownership.FieldOwnershipPolicy:
    """The policy this invocation judges by: an explicit file, or the committed one."""
    explicit = getattr(args, "policy", None)
    if explicit:
        document = yaml.safe_load(Path(explicit).read_text(encoding="utf-8"))
        return ownership.FieldOwnershipPolicy.from_document(document)
    return ownership.load_policy(_root(args))


def _fail(report: str) -> int:
    print(report, file=sys.stderr)
    return 1


def _cmd_ownership_check(args) -> int:
    try:
        explicit = getattr(args, "policy", None)
        document = (
            yaml.safe_load(Path(explicit).read_text(encoding="utf-8")) if explicit
            else ownership.load_document(_root(args))
        )
        report = ownership.check_coverage(document)
    except (OwnershipError, PolicyNotFound) as exc:
        return _fail(f"ERROR: {exc}")
    if not report.ok:
        return _fail(report.render())
    print(report.render())
    return 0


def _cmd_field_writer(args) -> int:
    from atdd.state import merge_authority  # local: keeps the import surface small

    repo = _root(args)
    try:
        policy = _policy(args)
        base_sha = merge_authority.merge_base(repo, args.base, args.head) if args.base else None
        base = merge_authority.projection_at(repo, base_sha)
        head = merge_authority.projection_at(repo, args.head)
        actor = args.actor if args.actor is not None else _git_author(repo, args.head)
    except (OwnershipError, PolicyNotFound, merge_authority.MergeAuthorityError) as exc:
        return _fail(f"ERROR: {exc}")
    report = ownership.check_diff(policy, base, head, actor=actor)
    if not report.ok:
        return _fail(report.render())
    print(report.render())
    return 0


def _git_author(repo: Path, ref: str) -> str:
    """The identity that authored a commit — ``Name <email>``, git's own answer."""
    from atdd.state import merge_authority

    return merge_authority.commit_author(repo, ref)


def _cmd_merge_projection(args) -> int:
    repo = _root(args)
    try:
        policy = _policy(args)
    except (OwnershipError, PolicyNotFound) as exc:
        return _fail(f"ERROR: {exc}")

    uid = _uid_of(args)
    ours_evidence = _evidence(args.ours_evidence, repo, uid, "HEAD")
    theirs_evidence = _evidence(args.theirs_evidence, repo, uid, _incoming_ref(repo))
    try:
        result = merge_driver.merge_files(
            Path(args.base) if args.base else None,
            Path(args.ours),
            Path(args.theirs),
            output=Path(args.output) if args.output else None,
            policy=policy,
            ours_evidence=ours_evidence,
            theirs_evidence=theirs_evidence,
        )
    except MergeDriverError as exc:
        return _fail(f"ERROR: {exc}")
    if not result.ok:
        return _fail(result.render())
    print(result.render())
    return 0


def _uid_of(args) -> str:
    """The object being merged. Git hands the driver temp files, so the *path* is not the uid.

    ``%A`` is a temp name during a real merge; the uid is what the document says it is, and
    the document is the only place it is authoritative anyway (spec §10 rule 1).
    """
    for candidate in (args.ours, args.theirs, args.base):
        if not candidate:
            continue
        try:
            document = yaml.safe_load(Path(candidate).read_text(encoding="utf-8"))
        except OSError:
            continue
        if isinstance(document, dict) and document.get("uid"):
            return str(document["uid"])
    return Path(args.ours).stem


#: How git tells a merge driver which commit the *other* side is: it exports one
#: ``GITHEAD_<sha>=<branch>`` per merge head into the driver's environment. There is no
#: ``MERGE_HEAD`` yet while a driver runs — git writes that only once the merge has stopped.
_GITHEAD_RE = re.compile(r"^GITHEAD_([0-9a-f]{40})$")


def _incoming_ref(repo: Path) -> str:
    """The commit *theirs* comes from, as git advertises it to a merge driver."""
    from atdd.state import merge_authority

    try:
        head = merge_authority._git(repo, "rev-parse", "HEAD").strip()  # noqa: PLC2701
    except merge_authority.MergeAuthorityError:
        head = ""
    for key in sorted(os.environ):
        match = _GITHEAD_RE.match(key)
        if match and match.group(1) != head:
            return match.group(1)
    return "MERGE_HEAD"  # a rebase/cherry-pick, where git does publish it


def _evidence(explicit: Optional[str], repo: Path, uid: str, ref: str) -> List[str]:
    """The gate evidence a side of the merge carries.

    Explicit tokens win; otherwise they are read from that side's **committed** evidence
    artifact, ``.atdd/evidence/<uid>.yaml``, out of the git object database at that side's
    commit. That the artifact must be *committed* is the point rather than an implementation
    detail: evidence a merge cannot see is evidence the merge does not have (spec §6), and a
    side's evidence is not in the worktree while the driver runs.
    """
    if explicit is not None:
        return [token.strip() for token in explicit.split(",") if token.strip()]
    return _evidence_at(repo, uid, ref)


def _evidence_at(repo: Path, uid: str, ref: str) -> List[str]:
    """Every evidence token committed for ``uid`` at ``ref``, unioned.

    Evidence is **sharded per gate** — ``.atdd/evidence/<uid>/<gate>.yaml`` — for the same
    reason the projection is sharded per uid: two developers who evidenced two different
    transitions of one object wrote two different files, and two different files merge. A
    single ``<uid>.yaml`` accumulating every gate would collide on every concurrent advance,
    and the merge would fail on the *evidence* rather than on the object it evidences.

    The flat ``<uid>.yaml`` form is still read, so an object with one gate to show for itself
    needs no directory.
    """
    from atdd.state.merge_authority import MergeAuthorityError, _git  # noqa: PLC2701 — same package

    prefix = (EVIDENCE_RELATIVE / uid).as_posix()
    try:
        listing = _git(repo, "ls-tree", "-r", "--name-only", ref, "--", prefix, f"{prefix}.yaml")
    except MergeAuthorityError:
        return []  # no such ref (or no such tree): that side carries no evidence
    tokens: List[str] = []
    for path in sorted(line.strip() for line in listing.splitlines() if line.strip()):
        try:
            tokens.extend(_tokens(_git(repo, "show", f"{ref}:{path}")))
        except MergeAuthorityError:
            continue
    return tokens


def _tokens(text: str) -> List[str]:
    """The tokens an evidence artifact declares: a YAML list, or ``{evidence: [...]}``."""
    document = yaml.safe_load(text)
    if isinstance(document, dict):
        document = document.get("evidence", [])
    if not isinstance(document, list):
        return []
    return [str(token) for token in document]


def _cmd_merge_matrix_check(args) -> int:
    try:
        policy = ownership.load_policy(_root(args))
    except (OwnershipError, PolicyNotFound) as exc:
        return _fail(f"ERROR: {exc}")
    report = merge_matrix.check_coverage(policy=policy)
    if not report.ok:
        return _fail(report.render())
    print(report.render())
    return 0


def _cmd_compact_archive(args) -> int:
    from atdd.state.projection_cli import _projection_dir  # noqa: PLC2701 — same package

    projection_dir = _projection_dir(args)
    removed = tombstone.compact_archive(projection_dir, uids=args.uid)
    print(
        f"archival compaction removed {len(removed)} tombstoned object(s): {removed}"
        if removed else "archival compaction removed nothing (no tombstoned object matched)"
    )
    return 0


def dispatch(args) -> int:
    """Run the field-governance verb named by ``args.op``."""
    handlers = {
        "ownership-check": _cmd_ownership_check,
        "field-writer": _cmd_field_writer,
        "merge-projection": _cmd_merge_projection,
        "merge-matrix-check": _cmd_merge_matrix_check,
        "compact-archive": _cmd_compact_archive,
    }
    return handlers[args.op](args)
