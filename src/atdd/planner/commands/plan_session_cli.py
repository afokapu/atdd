"""`atdd plan <op>` — the harness CLI that drives the gated decomposition
session (#1139 slice 4).

The LLM/agent calls these ops between conversation turns; each op loads the
durable session, applies one deterministic mutation, saves, and prints the
session state as JSON to stdout so the agent can read it. keep/pivot/kill flows
through the #1096a `elicit` contract (an inline Claude adapter here); on
`confirm` the session locks; `author` invokes the #1144 writers per kept unit
(the conversational->deterministic boundary). Stdlib + plan_session + elicit.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

from atdd.planner.commands.author import AuthorInputError, validate_author_spec
from atdd.planner.commands.plan_session import (
    PlanSession, SessionGateError, Step, Unit, build_author_fn,
)
from atdd.runtime.elicit import (
    AtddRole, ElicitResponse, ElicitRole, ElicitStatus, InlineClaudeElicitAdapter,
    Participant,
)


def _state(s: PlanSession) -> dict:
    return {
        "session_id": s.session_id,
        "step": s.step,
        "main_job": s.main_job,
        "issue_ref": s.issue_ref,
        "locked": s.locked,
        "sources": s.sources,
        "units": [
            {"kind": u["kind"], "ref": u["ref"], "verdict": u["verdict"],
             "modification": u.get("modification")}
            for u in s.units
        ],
    }


def _emit(payload: dict) -> int:
    print(json.dumps(payload, sort_keys=True))
    return 0


_SPEC_FILE_SUFFIXES = (".json", ".yaml", ".yml")


def _looks_like_a_path(raw: str) -> bool:
    """True when ``raw`` reads as a filesystem path an operator meant to pass."""
    return raw.endswith(_SPEC_FILE_SUFFIXES) or Path(raw).exists()


def _parse_spec(raw: str) -> dict:
    """Resolve the ``--spec`` argument to an author-spec dict, or refuse.

    Accepts an inline JSON object, or the explicit ``@<path>`` form that reads
    the object from a file. A bare path is refused with a hint naming ``@``
    rather than autodetected: autodetection would make the meaning of ``--spec``
    depend on filesystem state, so the same command would behave differently on
    two machines. A leading ``@`` is never legal JSON, so the form can never
    collide with an inline spec.

    Raises ``AuthorInputError`` (field ``spec``); the caller maps it to exit 2.
    """
    if raw.startswith("@"):
        path = raw[1:]
        if not path:
            raise AuthorInputError("spec", "the @ form needs a path: --spec @<path>")
        try:
            text = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            raise AuthorInputError("spec", f"cannot read spec file {path!r}: {exc}") from None
    else:
        text = raw

    try:
        spec = json.loads(text)
    except json.JSONDecodeError as exc:
        hint = ""
        if not raw.startswith("@") and _looks_like_a_path(raw):
            hint = f"; to read a spec from a file use --spec @{raw}"
        source = f"spec file {raw[1:]!r}" if raw.startswith("@") else "--spec"
        raise AuthorInputError("spec", f"{source} is not valid JSON: {exc}{hint}") from None

    validate_author_spec(spec)
    return spec


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="atdd plan",
                                description="Drive the atdd plan gated decomposition session.")
    p.add_argument("--root", default=".", help="repo root the session persists under (default: cwd)")
    sub = p.add_subparsers(dest="op", required=True)

    def with_id(sp):
        sp.add_argument("--id", required=True, dest="session_id")

    sub.add_parser("guidelines", help="assemble the agent working context (session + decomposition protocol nodes)")
    s = sub.add_parser("start", help="create a new session"); with_id(s)
    s.add_argument("--main-job", default=None, dest="main_job")
    s.add_argument("--issue", default=None, dest="issue_ref",
                   help="bind the plan to this local ATDD issue (manifest slug; not a GitHub number)")
    bi = sub.add_parser("bind-issue", help="bind the plan to a local ATDD issue (required before confirm)"); with_id(bi)
    bi.add_argument("--issue", dest="issue_ref", required=True,
                    help="local ATDD issue identity (manifest slug); the GitHub number is a synced projection")
    with_id(sub.add_parser("show", help="print session state"))
    mj = sub.add_parser("main-job", help="set the JTBD main job (Define)"); with_id(mj); mj.add_argument("text")
    sc = sub.add_parser("source", help="capture a source (Locate)"); with_id(sc); sc.add_argument("text")
    un = sub.add_parser("unit", help="add a candidate unit (Prepare)"); with_id(un)
    un.add_argument("--kind", required=True); un.add_argument("--ref", required=True)
    un.add_argument("--spec", default="{}",
                    help="inline JSON object atdd-author spec for the unit, "
                         "or @<path> to read the object from a file")
    ad = sub.add_parser("advance", help="advance to a step"); with_id(ad)
    ad.add_argument("--step", required=True, choices=[s.value for s in Step])
    de = sub.add_parser("decide", help="keep/pivot/kill a unit via the elicit channel"); with_id(de)
    de.add_argument("--ref", required=True); de.add_argument("--verdict", required=True, choices=["keep", "pivot", "kill"])
    de.add_argument("--mod", default=None, dest="modification")
    with_id(sub.add_parser("confirm", help="lock the decomposition (confirm-before-author boundary)"))
    with_id(sub.add_parser("reopen", help="withdraw the confirmation and return to Prepare "
                                          "(the sanctioned way to edit a locked session)"))
    with_id(sub.add_parser("author", help="author kept units via atdd author (post-confirm)"))
    return p


def _resolver_for(verdict: str, modification: str | None):
    def _r(req):
        return ElicitResponse(
            elicit_id=req.elicit_id, status=ElicitStatus.RESOLVED,
            resolved_by=Participant(ElicitRole.OPERATOR, "user"),
            selections=[verdict], freeform=modification,
        )
    return InlineClaudeElicitAdapter(_r)


def run(argv: list[str]) -> int:
    args = build_parser().parse_args(argv)
    root = args.root
    try:
        if args.op == "guidelines":
            from atdd.planner.commands.plan_context import load_working_context
            return _emit(load_working_context(root))
        if args.op == "start":
            s = PlanSession(args.session_id, main_job=args.main_job, issue_ref=args.issue_ref)
            s.save(root)
            return _emit(_state(s))

        s = PlanSession.load(args.session_id, root)
        if args.op == "show":
            return _emit(_state(s))
        if args.op == "bind-issue":
            s.assert_mutable("re-bind the issue")  # #1505: the lock covers the whole session
            s.issue_ref = args.issue_ref
        elif args.op == "main-job":
            s.assert_mutable("change the main job")
            s.main_job = args.text
        elif args.op == "source":
            s.assert_mutable("capture another source")
            s.sources.append({"type": "text", "value": args.text})
        elif args.op == "reopen":
            s.reopen()
        elif args.op == "unit":
            s.add_unit(Unit(kind=args.kind, ref=args.ref, spec=_parse_spec(args.spec)))
        elif args.op == "advance":
            s.advance(Step(args.step))
        elif args.op == "decide":
            s.decide(args.ref, _resolver_for(args.verdict, args.modification))
        elif args.op == "confirm":
            s.confirm()
        elif args.op == "author":
            authored = s.author(build_author_fn(root))
            s.save(root)
            return _emit({**_state(s), "authored": [str(p) for p in authored]})
        s.save(root)
        return _emit(_state(s))
    except SessionGateError as exc:
        logger.warning("atdd plan gate refused op", extra={"op": getattr(args, "op", None), "error": str(exc)})
        print(f"atdd plan: {exc}", file=sys.stderr)
        return 2
    except AuthorInputError as exc:
        logger.warning("atdd plan refused a malformed argument",
                       extra={"op": getattr(args, "op", None), "field": exc.field, "error": str(exc)})
        print(f"atdd plan: invalid --{exc.field}: {exc}", file=sys.stderr)
        return 2
