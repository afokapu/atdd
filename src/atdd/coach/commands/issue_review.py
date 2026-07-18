"""`atdd issue review` — multi-pass cross-LLM review of an ATDD parent issue.

Per spec §5.6 / §6.10 (and issue #508): pre-coach must produce a
meta-review of an ATDD parent issue body before coach starts work.
A single-LLM review inherits that LLM's training-data biases (missed
ambiguities, missed regression risks, missed comprehensiveness gaps), so
the contract is N independent passes (default 3, min 2), each by a
*different* LLM, each evaluating the same five dimensions:

    systemic, ambiguities, gap, regression, comprehensiveness

Per-pass payloads land at::

    .atdd/runtime/issue-reviews/<N>/pass-<i>-<llm>.json

(schema: ``issue-review-pass.response.schema.json``) — pass ``i`` is
produced by ``--llms[i-1]`` so re-runs are reproducible.

The cross-pass roll-up lands at::

    .atdd/runtime/issue-reviews/<N>/aggregate.json

(schema: ``issue-review-aggregate.schema.json``). The §4.2 pre-coach
precondition reads it and routes per its top-level ``verdict``:

  * ``unanimous-pass``     → coach proceeds.
  * ``mixed-verdict``      → judge call site #5 (per #O3) for consolidation.
  * ``unanimous-concern``  → coach transitions to BLOCKED.

Per spec §6.10 systemic concerns dominate: a single pass surfacing a
systemic concern collapses the verdict to ``unanimous-concern`` even if
the other passes were silent on it.

Public API:
  - ``run(*, issue_number, passes, llms, dimensions, show, force) -> int``
  - ``parse_cli(argv)`` — argparse over the §5.6 surface
  - ``classify_aggregate(agg) -> Literal["proceed", "request-judge", "block"]``
  - ``route_aggregate_to_judge(agg, *, judge_fn)`` — adapter for #O3
  - ``post_issue_comment(issue_number, body)`` — GitHub-comment writer for ``--show``
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, List, Literal, Optional

import jsonschema

from atdd.coach.commands.llm_clients import registry as llm_registry
from atdd.coach.commands.issue_graph import build_issue_architecture_context
from atdd.coach.utils.coach_config import load_coach_config
from atdd.coach.utils.rule_binding import bind_rule, RuleNotInRegistryError


# Used by tests as a single seam for "rule lookup failed" — kept aliased
# here so callers can monkeypatch a single name regardless of how
# rule_binding's internal exception hierarchy evolves.
RuleBindingError = RuleNotInRegistryError


DIMENSIONS: tuple[str, ...] = (
    "systemic",
    "ambiguities",
    "gap",
    "regression",
    "comprehensiveness",
)


_REPO_ROOT_FALLBACK = Path.cwd()


def _resolve_repo_root() -> Path:
    """Walk up from cwd until a `.atdd/` directory is found.

    Mirrors the helper in ``commands.judge`` (intentional duplication so
    each command owns its own root-resolution policy and tests can chdir
    into tmp_path workspaces without cross-test bleed).
    """
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / ".atdd").is_dir():
            return current
        current = current.parent
    return _REPO_ROOT_FALLBACK


# ---------------------------------------------------------------------------
# Schemas (loaded lazily; tests rely on the on-disk frozen contracts)
# ---------------------------------------------------------------------------


_SCHEMAS_DIR = Path(__file__).resolve().parents[1] / "schemas"


def _pass_schema() -> dict:
    return json.loads(
        (_SCHEMAS_DIR / "issue-review-pass.response.schema.json").read_text()
    )


def _aggregate_schema() -> dict:
    return json.loads(
        (_SCHEMAS_DIR / "issue-review-aggregate.schema.json").read_text()
    )


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


@dataclass
class IssueReviewConfig:
    issue_number: int
    passes: Optional[int] = None
    llms: Optional[List[str]] = None
    dimensions: Optional[List[str]] = None
    show: bool = False
    force: bool = False


def _csv(value: str) -> List[str]:
    return [v.strip() for v in value.split(",") if v.strip()]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd coach issue-review",
        description=(
            "Multi-pass cross-LLM review of an ATDD parent issue body. "
            "Runs N independent passes (default 3, min 2) by distinct LLMs, "
            "evaluates each across the five fixed dimensions (systemic, "
            "ambiguities, gap, regression, comprehensiveness), and writes "
            "per-pass + aggregate JSON under .atdd/runtime/issue-reviews/<N>/. "
            "Consumed by the §4.2 pre-coach precondition."
        ),
    )
    parser.add_argument(
        "issue_number",
        type=int,
        help="GitHub issue number to review.",
    )
    parser.add_argument(
        "--passes",
        type=int,
        default=None,
        help="Number of independent passes (default from coach config; minimum 2).",
    )
    parser.add_argument(
        "--llms",
        type=_csv,
        default=None,
        help="Comma-separated LLM client ids registered in the shared judge registry.",
    )
    parser.add_argument(
        "--dimensions",
        type=_csv,
        default=None,
        help=(
            "Comma-separated dimensions to evaluate (default: all five "
            "from spec §6.10)."
        ),
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Post the aggregate as a GitHub comment on the issue.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run all passes even when per-pass files already exist.",
    )
    return parser


def parse_cli(argv: List[str]) -> IssueReviewConfig:
    ns = _build_parser().parse_args(argv)
    return IssueReviewConfig(
        issue_number=ns.issue_number,
        passes=ns.passes,
        llms=ns.llms,
        dimensions=ns.dimensions,
        show=ns.show,
        force=ns.force,
    )


# ---------------------------------------------------------------------------
# Prompt rendering
# ---------------------------------------------------------------------------


def _fetch_issue_body(issue_number: int) -> str:
    """Fetch the GitHub issue body host-side via ``gh issue view``.

    Per issue #721: the review LLM runs sandboxed with no ``gh``, so the
    host resolves the body once and injects it inline into every pass
    prompt. On any ``gh`` failure this degrades gracefully to a short
    placeholder rather than aborting the whole review.
    """
    try:
        proc = subprocess.run(
            ["gh", "issue", "view", str(issue_number),
             "--json", "body", "--jq", ".body"],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return f"(issue #{issue_number} body unavailable — `gh issue view` could not be run)"
    if proc.returncode != 0:
        return f"(issue #{issue_number} body unavailable — `gh issue view` exited {proc.returncode})"
    return proc.stdout.strip()


def _render_context_sections(
    *,
    issue_number: int,
    issue_body: str,
    graph_context: Optional[str],
) -> List[str]:
    """Render the host-injected context lines for one review pass (issue #721).

    The sandboxed review LLM has no ``gh``, so the host splices the issue
    body inline and — when the issue maps to a wagon — an ``atdd repo``
    graph summary the ``systemic`` dimension is directed to consume.
    Returns the section lines to be joined into the per-pass prompt.
    """
    sections = [
        f"--- ISSUE #{issue_number} BODY (verbatim) ---",
        issue_body,
        f"--- END ISSUE #{issue_number} BODY ---",
        "",
    ]
    if graph_context:
        sections += [
            graph_context,
            "",
            "For the `systemic` dimension, ground your verdict (one-off "
            "patch vs systemic pattern) in the Architecture context above "
            "— not the issue text alone.",
            "",
        ]
    return sections


def _render_prompt(
    *,
    issue_number: int,
    dimensions: List[str],
    llm_id: str,
    issue_body: str,
    graph_context: Optional[str] = None,
) -> str:
    """Render the per-pass prompt.

    Per spec §6.10 the per-pass review is bounded by the five fixed
    dimensions; track owners may evolve the prompt body in conventions,
    but the contract surface (issue id + dimensions) is owned here. The
    host-injected context (issue body + ``atdd repo`` graph summary, per
    issue #721) is delegated to :func:`_render_context_sections`.
    """
    dim_list = "\n".join(f"  - {d}" for d in dimensions)
    return "\n".join([
        f"Review ATDD issue #{issue_number} across these dimensions:",
        dim_list,
        "",
        *_render_context_sections(
            issue_number=issue_number,
            issue_body=issue_body,
            graph_context=graph_context,
        ),
        f"Reviewer LLM: {llm_id}",
        "Return JSON of shape {\"dimensions\": {<dim>: {\"verdict\": "
        "\"pass\"|\"concern\", \"findings\": [...]}}}.",
    ])


# ---------------------------------------------------------------------------
# Per-pass write path
# ---------------------------------------------------------------------------


def _runtime_dir(repo_root: Path, issue_number: int) -> Path:
    return repo_root / ".atdd" / "runtime" / "issue-reviews" / str(issue_number)


def _pass_path(repo_root: Path, issue_number: int, pass_id: int, llm_id: str) -> Path:
    return _runtime_dir(repo_root, issue_number) / f"pass-{pass_id}-{llm_id}.json"


def _atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    os.replace(tmp, path)


def _resolve_finding_rule_ids(record: dict) -> None:
    """Replace each finding's `rule_id` with its canonical id, or null.

    Per issue body: "When a finding maps to a known rule-ID via
    `bind_rule()`, the `rule_id` field is populated; otherwise `null`."
    Unknown ids (LLM hallucinations) are erased rather than propagated.
    """
    for dim, evaluation in record["dimensions"].items():
        for finding in evaluation.get("findings", []):
            rid = finding.get("rule_id")
            if rid is None:
                continue
            try:
                meta = bind_rule(rid)
            except RuleBindingError:
                finding["rule_id"] = None
                continue
            # bind_rule may return alias→canonical; record the canonical form.
            finding["rule_id"] = getattr(meta, "rule_id", rid)


def _build_pass_record(
    *,
    issue_number: int,
    pass_id: int,
    llm_id: str,
    raw_response: dict,
) -> dict:
    """Wrap raw LLM dimensions payload with required identity fields."""
    if not isinstance(raw_response, dict) or "dimensions" not in raw_response:
        raise ValueError(
            f"LLM {llm_id!r} returned a payload without a `dimensions` field"
        )
    record = {
        "pass_id": pass_id,
        "issue": issue_number,
        "llm": llm_id,
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "dimensions": raw_response["dimensions"],
    }
    return record


def _validate_pass_record(record: dict) -> None:
    jsonschema.Draft202012Validator(_pass_schema()).validate(record)


# ---------------------------------------------------------------------------
# Aggregate
# ---------------------------------------------------------------------------


def _build_aggregate(*, issue_number: int, pass_records: List[dict]) -> dict:
    per_dim: dict = {}
    findings: list = []
    seen_dedup: set = set()
    for dim in DIMENSIONS:
        concern_passes = [
            rec["pass_id"]
            for rec in pass_records
            if rec["dimensions"][dim]["verdict"] == "concern"
        ]
        per_dim[dim] = {
            "verdict": "concern" if concern_passes else "pass",
            "concern_passes": concern_passes,
        }

    for rec in pass_records:
        for dim in DIMENSIONS:
            for finding in rec["dimensions"][dim].get("findings", []):
                rid = finding.get("rule_id")
                detail = finding["detail"]
                # Dedup only when both rule_id and detail are populated
                # (per issue body). Otherwise list every finding.
                key = None
                if rid is not None and detail:
                    key = (rid, detail)
                    if key in seen_dedup:
                        continue
                    seen_dedup.add(key)
                findings.append({
                    "pass_id": rec["pass_id"],
                    "llm": rec["llm"],
                    "dimension": dim,
                    "rule_id": rid,
                    "severity": finding["severity"],
                    "detail": detail,
                })

    total_passes = len(pass_records)
    verdict = _classify_verdict(per_dim, total_passes=total_passes)

    aggregate = {
        "issue": issue_number,
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "passes": [
            {
                "pass_id": rec["pass_id"],
                "llm": rec["llm"],
                "timestamp": rec["timestamp"],
            }
            for rec in pass_records
        ],
        "dimensions": per_dim,
        "verdict": verdict,
        "findings": findings,
    }
    return aggregate


def _classify_verdict(per_dim: dict, *, total_passes: int) -> str:
    """Top-level routing label per spec §6.10.

    Systemic dominates: any pass surfacing a systemic concern collapses
    the verdict to ``unanimous-concern`` regardless of other dimensions.
    Otherwise: unanimous-pass when no dimension has any concern;
    unanimous-concern when every concerned dimension was flagged by every
    pass; mixed-verdict when at least one concerned dimension was flagged
    by a strict subset of the passes (passes disagreed).
    """
    if per_dim["systemic"]["verdict"] == "concern":
        return "unanimous-concern"

    any_concern = any(per_dim[d]["verdict"] == "concern" for d in DIMENSIONS)
    if not any_concern:
        return "unanimous-pass"

    expected = set(range(1, total_passes + 1))
    for d in DIMENSIONS:
        if per_dim[d]["verdict"] == "concern":
            if set(per_dim[d]["concern_passes"]) != expected:
                return "mixed-verdict"
    return "unanimous-concern"


def classify_aggregate(aggregate: dict) -> Literal["proceed", "request-judge", "block"]:
    """Map aggregate verdict to the §4.2 pre-coach routing decision."""
    verdict = aggregate["verdict"]
    if verdict == "unanimous-pass":
        return "proceed"
    if verdict == "mixed-verdict":
        return "request-judge"
    return "block"


# ---------------------------------------------------------------------------
# Judge routing adapter (#O3 consumes this)
# ---------------------------------------------------------------------------


def route_aggregate_to_judge(
    aggregate: dict,
    *,
    judge_fn: Callable[[str, dict], dict],
) -> dict:
    """Route a mixed-verdict aggregate to judge call site #5 exactly once.

    For unanimous aggregates the routing decision is final; the judge
    function is not called. For mixed-verdict aggregates ``judge_fn`` is
    invoked once with ``call_site="review-disposition"`` (the §6.9 site
    that #O3 owns) and a payload carrying the aggregate. The return is
    surfaced verbatim so #O3 can shape the response policy.
    """
    decision = classify_aggregate(aggregate)
    if decision == "proceed":
        return {"decision": "proceed"}
    if decision == "block":
        return {"decision": "block"}
    return judge_fn("review-disposition", {"aggregate": aggregate})


# ---------------------------------------------------------------------------
# GitHub-comment surface (--show, and pre-coach `request_revision`)
# ---------------------------------------------------------------------------


def _format_aggregate_comment(aggregate: dict) -> str:
    """Render the aggregate as a markdown body for the GitHub comment."""
    lines = ["## ATDD issue review — multi-pass aggregate", ""]
    lines.append(f"**Verdict:** `{aggregate['verdict']}`")
    lines.append("")
    lines.append("| Dimension | Verdict | Concerned passes |")
    lines.append("|---|---|---|")
    for dim in DIMENSIONS:
        d = aggregate["dimensions"][dim]
        cp = ", ".join(str(p) for p in d["concern_passes"]) or "—"
        lines.append(f"| `{dim}` | `{d['verdict']}` | {cp} |")
    findings = aggregate.get("findings") or []
    if findings:
        lines.append("")
        lines.append("### Findings")
        for f in findings:
            rid = f"`{f['rule_id']}`" if f.get("rule_id") else "_(no rule binding)_"
            lines.append(
                f"- pass {f['pass_id']} (`{f['llm']}`) · `{f['dimension']}` · "
                f"severity {f['severity']} · {rid} · {f['detail']}"
            )
    lines.append("")
    lines.append("Passes:")
    for p in aggregate["passes"]:
        lines.append(f"- pass {p['pass_id']} · `{p['llm']}` · {p['timestamp']}")
    return "\n".join(lines)


def post_issue_comment(*, issue_number: int, body: str) -> int:
    """Post `body` as a GitHub comment on `issue_number` via `gh issue comment`.

    Tests monkeypatch this seam to capture the body without shelling out
    to a real `gh`.
    """
    proc = subprocess.run(
        ["gh", "issue", "comment", str(issue_number), "--body", body],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        sys.stderr.write(
            f"gh issue comment failed (rc={proc.returncode}): {proc.stderr}\n"
        )
    return proc.returncode


# ---------------------------------------------------------------------------
# Core run
# ---------------------------------------------------------------------------


def _print_error(msg: str) -> None:
    sys.stderr.write(msg + "\n")


def run(
    *,
    issue_number: int,
    passes: Optional[int] = None,
    llms: Optional[List[str]] = None,
    dimensions: Optional[List[str]] = None,
    show: bool = False,
    force: bool = False,
) -> int:
    """Execute one `atdd issue review` invocation. Returns the process exit code."""
    repo_root = _resolve_repo_root()
    cfg = load_coach_config(repo_root)
    review_cfg = cfg.issue_review

    effective_passes = passes if passes is not None else review_cfg.passes
    effective_llms = list(llms) if llms else list(review_cfg.llms)
    effective_dims = list(dimensions) if dimensions else list(review_cfg.dimensions)

    # 1. Minimum-2 floor (single-LLM-once is inadmissible per spec §6.10).
    if effective_passes < 2:
        _print_error(
            f"--passes must be >= 2 (got {effective_passes}). "
            f"Single-LLM review is inadmissible per spec §6.10 "
            f"(minimum two independent passes required)."
        )
        return 2

    # 2. Insufficient distinct LLMs.
    if effective_passes > len(effective_llms):
        _print_error(
            f"--passes={effective_passes} requires at least {effective_passes} "
            f"distinct --llms entries; got {len(effective_llms)} "
            f"(insufficient llms: {effective_llms!r})."
        )
        return 2

    # 3. Dimension validation (closed set).
    unknown_dims = [d for d in effective_dims if d not in DIMENSIONS]
    if unknown_dims:
        _print_error(
            f"unknown --dimensions {unknown_dims!r}; "
            f"expected subset of {list(DIMENSIONS)}."
        )
        return 2

    # 4. Resolve the issue body + repo-graph neighbourhood host-side once
    #    (issue #721): the sandboxed review LLM has no `gh`, so the host
    #    fetches the body and the `atdd repo` graph summary and injects
    #    both inline into every pass prompt.
    issue_body = _fetch_issue_body(issue_number)
    graph_context = build_issue_architecture_context(
        issue_number, repo_root=repo_root
    )

    # 5. Resolve pass identities and the LLM registry.
    pass_records: list[dict] = []
    for i in range(1, effective_passes + 1):
        llm_id = effective_llms[i - 1]
        path = _pass_path(repo_root, issue_number, i, llm_id)

        if path.exists() and not force:
            record = json.loads(path.read_text())
            pass_records.append(record)
            continue

        factory = llm_registry.LLM_REGISTRY.get(llm_id)
        if factory is None:
            _print_error(
                f"unknown LLM id {llm_id!r}; not in registry "
                f"(known: {sorted(llm_registry.LLM_REGISTRY)})."
            )
            return 3

        try:
            client = factory()
            raw = client.invoke(_render_prompt(
                issue_number=issue_number,
                dimensions=effective_dims,
                llm_id=llm_id,
                issue_body=issue_body,
                graph_context=graph_context,
            ))
        except llm_registry.LLMUnavailable as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            _print_error(f"LLM unavailable ({llm_id!r}): {exc}")
            return 5

        try:
            record = _build_pass_record(
                issue_number=issue_number,
                pass_id=i,
                llm_id=llm_id,
                raw_response=raw if isinstance(raw, dict) else {},
            )
        except ValueError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            _print_error(f"pass {i}/{llm_id} invalid response: {exc}")
            return 4

        # Schema-validate the record *before* touching the rule-binding
        # path (issue #721): a parseable-but-malformed payload — e.g. a
        # dimension value or `findings` entry that is a `str` where a
        # dict/array is expected — is rejected here as a clean,
        # field-naming schema violation instead of crashing
        # `_resolve_finding_rule_ids` with an unhandled AttributeError.
        try:
            _validate_pass_record(record)
        except jsonschema.ValidationError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            field = ".".join(str(p) for p in exc.absolute_path) or "<root>"
            _print_error(
                f"pass {i}/{llm_id} schema violation at {field!r}: {exc.message}"
            )
            return 4

        # Shape is now schema-guaranteed; resolve / scrub finding rule_ids.
        # The schema admits ``null`` so any unknown id is normalized in
        # place without needing re-validation.
        try:
            _resolve_finding_rule_ids(record)
        except Exception as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            _print_error(f"pass {i}/{llm_id} rule binding failed: {exc}")
            return 4

        _atomic_write_json(path, record)
        pass_records.append(record)

    # 6. Aggregate.
    aggregate = _build_aggregate(
        issue_number=issue_number, pass_records=pass_records
    )
    try:
        jsonschema.Draft202012Validator(_aggregate_schema()).validate(aggregate)
    except jsonschema.ValidationError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        field = ".".join(str(p) for p in exc.absolute_path) or "<root>"
        _print_error(
            f"aggregate schema violation at {field!r}: {exc.message}"
        )
        return 4

    aggregate_path = _runtime_dir(repo_root, issue_number) / "aggregate.json"
    _atomic_write_json(aggregate_path, aggregate)

    # 7. --show: surface the aggregate on the GitHub issue.
    if show:
        post_issue_comment(
            issue_number=issue_number,
            body=_format_aggregate_comment(aggregate),
        )

    print(json.dumps(aggregate, ensure_ascii=False))
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    cfg = parse_cli(list(sys.argv[1:] if argv is None else argv))
    return run(
        issue_number=cfg.issue_number,
        passes=cfg.passes,
        llms=cfg.llms,
        dimensions=cfg.dimensions,
        show=cfg.show,
        force=cfg.force,
    )
