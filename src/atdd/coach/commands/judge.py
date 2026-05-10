"""`atdd judge` — single boundary for ambiguous coach v9 routing decisions.

Per spec §5.5 / §6.9 (and issue #501): coach v9 calls a structured-output
LLM exactly here, with three guardrails:

  1. **Schema-validated response.** The caller supplies a JSON Schema;
     the LLM payload is validated before it is printed.
  2. **Audit trail.** Every invocation appends one line to
     ``.atdd/runtime/coach/judgments.jsonl`` conforming to
     ``coach-judgment.schema.json`` (frozen by #483).
  3. **Conservative fail-open governed by config.** When the LLM is
     unavailable (``LLMUnavailable``), behavior follows
     ``coach.judge.fail_open``: ``false`` (default) returns the per-call-site
     conservative fallback and exits 0; ``true`` returns nothing and exits
     non-zero so coach surfaces the gap. Both paths log to the JSONL
     under the same ``call_site``.

This module ships the **core**. The six v1 call sites (#O2/#O3/#O4) and
``atdd issue review`` (#O5) build on top of this surface; they share the
``LLM_REGISTRY`` here but contribute their own response schemas and
prompt templates.

Public API:
  - ``run(...)`` / ``main(argv)`` — CLI entry points
  - ``parse_cli(argv)`` — argparse over the §5.5 surface
  - ``register_llm_client(name, factory)`` — pluggable LLM clients
  - ``LLMClient`` — Protocol clients implement
  - ``LLMUnavailable`` — exception clients raise on outage
  - ``CALL_SITES`` — frozen set per spec §6.9
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

import jsonschema
import yaml

from atdd.coach.utils.coach_config import CoachConfig, load_coach_config


# Frozen at C0 to the six surfaces named in spec §6.9. New surfaces require
# an explicit follow-up issue per coach-judgment.schema.json.
CALL_SITES: tuple[str, ...] = (
    "phase-advance",
    "violation-suppression",
    "correction-injection",
    "review-disposition",
    "escalation",
    "merge-readiness",
    "borderline-tier1",
    "retry-vs-escalate",
    "cross-phase-regression",
    "issue-review-aggregate",
)

# Per-call-site conservative fallback when fail_open=false. Bias is toward
# blocking forward motion on routing-relevant sites (phase-advance,
# violation-suppression, review-disposition, merge-readiness) and toward
# escalating retry-vs-escalate / correction-injection so a human sees them.
_FALLBACK_DECISION: dict[str, str] = {
    "phase-advance":          "block",
    "violation-suppression":  "block",
    "correction-injection":   "escalate",
    "review-disposition":     "block",
    "escalation":             "escalate",
    "merge-readiness":        "block",
    "borderline-tier1":       "block",
    "retry-vs-escalate":      "escalate",
    "cross-phase-regression": "block",
    "issue-review-aggregate": "escalate",
}


# ---------------------------------------------------------------------------
# Pluggable LLM clients
# ---------------------------------------------------------------------------


class LLMUnavailable(Exception):
    """Raised by an LLM client when the model is unreachable.

    `atdd judge` catches this and routes to fail-open policy per
    ``coach.judge.fail_open`` (spec §6.9).
    """


class LLMClient(Protocol):
    """An LLM client invoked once per `atdd judge` call.

    Implementations may return any JSON-serializable Python value
    (dict / list / str / number / bool / None). The judge validates the
    return against the caller's JSON Schema before printing.
    """

    def invoke(self, prompt: str) -> Any: ...  # pragma: no cover - protocol


LLM_REGISTRY: dict[str, Callable[[], LLMClient]] = {}


def register_llm_client(name: str, factory: Callable[[], LLMClient]) -> None:
    """Register an LLM client factory under `name`.

    The factory is called once per `atdd judge` invocation. Tests register
    stubs here; production clients (#O2/#O5) register real clients at
    import time.
    """
    LLM_REGISTRY[name] = factory


# ---------------------------------------------------------------------------
# CLI surface (spec §5.5)
# ---------------------------------------------------------------------------


@dataclass
class JudgeConfig:
    prompt_template: str
    schema: str
    inputs: list[str]
    call_site: str
    llm: Optional[str] = None


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="atdd judge",
        description=(
            "Single boundary for ambiguous coach v9 routing decisions. "
            "Renders a prompt template, calls a structured-output LLM, "
            "validates the response, and appends an audit record to "
            ".atdd/runtime/coach/judgments.jsonl."
        ),
    )
    parser.add_argument(
        "--prompt-template",
        type=str,
        required=True,
        dest="prompt_template",
        help="YAML file with a top-level `prompt` field. Placeholders use {key}.",
    )
    parser.add_argument(
        "--schema",
        type=str,
        required=True,
        help="JSON Schema describing the expected LLM response shape.",
    )
    parser.add_argument(
        "--inputs",
        type=str,
        nargs="*",
        default=[],
        help="key=value or key=@file pairs substituted into the prompt template.",
    )
    parser.add_argument(
        "--call-site",
        type=str,
        required=True,
        dest="call_site",
        help=f"One of: {', '.join(CALL_SITES)}",
    )
    parser.add_argument(
        "--llm",
        type=str,
        default=None,
        help="LLM client id (registered via register_llm_client).",
    )
    return parser


def parse_cli(argv: list[str]) -> JudgeConfig:
    ns = _build_parser().parse_args(argv)
    return JudgeConfig(
        prompt_template=ns.prompt_template,
        schema=ns.schema,
        inputs=list(ns.inputs),
        call_site=ns.call_site,
        llm=ns.llm,
    )


# ---------------------------------------------------------------------------
# Input parsing and prompt rendering
# ---------------------------------------------------------------------------


def _parse_inputs(raw: list[str]) -> dict[str, str]:
    """Parse `key=val` and `key=@file` tokens into a {key: value} dict."""
    out: dict[str, str] = {}
    for token in raw:
        if "=" not in token:
            raise ValueError(
                f"--inputs token {token!r} must be key=value or key=@file"
            )
        key, value = token.split("=", 1)
        if not key:
            raise ValueError(f"--inputs token {token!r} has empty key")
        if value.startswith("@"):
            path = Path(value[1:])
            if not path.exists():
                raise FileNotFoundError(
                    f"--inputs file not found for key {key!r}: {path}"
                )
            value = path.read_text()
        out[key] = value
    return out


def _render_prompt(template_path: Path, inputs: dict[str, str]) -> str:
    """Read the prompt template YAML and substitute {key} placeholders."""
    raw = yaml.safe_load(template_path.read_text())
    if not isinstance(raw, dict) or "prompt" not in raw:
        raise ValueError(
            f"prompt template {template_path} must have a top-level `prompt` field"
        )
    body = raw["prompt"]
    if not isinstance(body, str):
        raise ValueError(
            f"prompt template {template_path}: `prompt` must be a string"
        )
    try:
        return body.format(**inputs)
    except KeyError as exc:
        raise ValueError(
            f"prompt template {template_path}: missing input for placeholder {exc.args[0]!r}"
        )


def _hash_inputs(call_site: str, inputs: dict[str, str]) -> str:
    """Stable hash of (call_site, normalized inputs). Same inputs → same hash."""
    payload = json.dumps(
        {"call_site": call_site, "inputs": inputs},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Audit trail
# ---------------------------------------------------------------------------


def _runtime_dir(repo_root: Path) -> Path:
    return repo_root / ".atdd" / "runtime" / "coach"


def _judgments_log(repo_root: Path) -> Path:
    return _runtime_dir(repo_root) / "judgments.jsonl"


def _inputs_cache_dir(repo_root: Path) -> Path:
    return _runtime_dir(repo_root) / "inputs-cache"


def _append_judgment(
    repo_root: Path,
    *,
    call_site: str,
    inputs_hash: str,
    response: Any,
    outcome: str,
    cached: bool = False,
    model: Optional[str] = None,
) -> None:
    record = {
        "judgment_id": str(uuid.uuid4()),
        "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "call_site": call_site,
        "inputs_hash": inputs_hash,
        "response": response,
        "cached": cached,
        "outcome": outcome,
    }
    if model is not None:
        record["model"] = model
    log_dir = _runtime_dir(repo_root)
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "judgments.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def _maybe_cache_inputs(
    repo_root: Path,
    *,
    inputs_hash: str,
    inputs: dict[str, str],
    log_full_inputs: bool,
) -> None:
    if not log_full_inputs:
        return
    cache_dir = _inputs_cache_dir(repo_root)
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / f"{inputs_hash}.json").write_text(
        json.dumps(inputs, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ---------------------------------------------------------------------------
# Core run
# ---------------------------------------------------------------------------


def _resolve_repo_root() -> Path:
    """Walk up from cwd until a .atdd/ directory is found.

    `atdd.coach.utils.repo.find_repo_root` is `lru_cache`d, which makes
    it unsuitable here: judge runs in tests under varying tmp_path
    fixtures and the cache poisons the second call. The judge audit log
    must land under the *current* repo's `.atdd/runtime/coach/`, so we
    walk the live cwd ourselves.
    """
    current = Path.cwd().resolve()
    while current != current.parent:
        if (current / ".atdd").is_dir():
            return current
        current = current.parent
    return Path.cwd().resolve()


def _print_response(response: Any) -> None:
    print(json.dumps(response, ensure_ascii=False))


def _print_error(msg: str) -> None:
    print(msg, file=sys.stderr)


def run(
    *,
    prompt_template: str,
    schema: str,
    inputs: list[str],
    call_site: str,
    llm: Optional[str] = None,
) -> int:
    """Execute one judge call. Returns the process exit code.

    The function never raises for documented failure modes (schema
    violation, LLM unavailable, missing @file): it logs to the JSONL,
    prints a diagnostic, and returns a non-zero exit code where
    appropriate. Truly unexpected exceptions propagate.
    """
    repo_root = _resolve_repo_root()
    cfg = load_coach_config(repo_root)

    # 1. Validate call_site up-front (no log entry — invocation never reached
    #    a judge surface).
    if call_site not in CALL_SITES:
        _print_error(
            f"unknown call_site {call_site!r}; expected one of {list(CALL_SITES)}"
        )
        return 2

    # 2. Resolve inputs (handles @file). Failures here are operator errors
    #    that occur before the LLM boundary, so we do not write a
    #    judgment record (the call never reached the judge surface).
    try:
        parsed_inputs = _parse_inputs(inputs)
    except (FileNotFoundError, ValueError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        _print_error(f"input resolution failed: {exc}")
        return 2

    # 3. Render the prompt template.
    try:
        prompt = _render_prompt(Path(prompt_template), parsed_inputs)
    except (FileNotFoundError, ValueError, yaml.YAMLError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        _print_error(f"prompt template error: {exc}")
        return 2

    # 4. Resolve the LLM client. Unknown id is an operator error, but we
    #    still log it as an llm_unavailable judgment so the audit trail
    #    captures the attempt (per spec §6.9 "audit trail does not lose
    #    the attempt").
    inputs_hash = _hash_inputs(call_site, parsed_inputs)
    _maybe_cache_inputs(
        repo_root,
        inputs_hash=inputs_hash,
        inputs=parsed_inputs,
        log_full_inputs=cfg.judge.log_full_inputs,
    )

    llm_id = llm or cfg.judge_llm
    factory = LLM_REGISTRY.get(llm_id)
    if factory is None:
        _append_judgment(
            repo_root,
            call_site=call_site,
            inputs_hash=inputs_hash,
            response=None,
            outcome="llm_unavailable",
            model=llm_id,
        )
        _print_error(
            f"unknown LLM id {llm_id!r}; not in registry "
            f"(known: {sorted(LLM_REGISTRY)})"
        )
        return 3

    # 5. Invoke the LLM.
    try:
        client = factory()
        response = client.invoke(prompt)
    except LLMUnavailable as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        return _handle_llm_unavailable(
            repo_root,
            cfg=cfg,
            call_site=call_site,
            inputs_hash=inputs_hash,
            llm_id=llm_id,
            reason=str(exc),
        )

    # 6. Validate against the caller's JSON Schema.
    try:
        schema_doc = json.loads(Path(schema).read_text())
    except (FileNotFoundError, json.JSONDecodeError) as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        _print_error(f"schema load error: {exc}")
        return 2

    try:
        jsonschema.Draft202012Validator(schema_doc).validate(response)
    except jsonschema.ValidationError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        field = ".".join(str(p) for p in exc.absolute_path) or "<root>"
        _append_judgment(
            repo_root,
            call_site=call_site,
            inputs_hash=inputs_hash,
            response=response,
            outcome="schema_violation",
            model=llm_id,
        )
        _print_error(
            f"schema validation failed at {field!r}: {exc.message}"
        )
        return 4

    # 7. Success.
    _append_judgment(
        repo_root,
        call_site=call_site,
        inputs_hash=inputs_hash,
        response=response,
        outcome="ok",
        model=llm_id,
    )
    _print_response(response)
    return 0


def _handle_llm_unavailable(
    repo_root: Path,
    *,
    cfg: CoachConfig,
    call_site: str,
    inputs_hash: str,
    llm_id: Optional[str],
    reason: str,
) -> int:
    """Apply coach.judge.fail_open policy when the LLM is unreachable."""
    if cfg.judge.fail_open:
        # Operator opted in to surface gaps loudly; no fallback response.
        _append_judgment(
            repo_root,
            call_site=call_site,
            inputs_hash=inputs_hash,
            response=None,
            outcome="llm_unavailable",
            model=llm_id,
        )
        _print_error(f"LLM unavailable ({llm_id!r}): {reason}")
        return 5

    # fail_open=false (default): return conservative per-call-site fallback.
    fallback = {
        "decision": _FALLBACK_DECISION[call_site],
        "fail_open_used": True,
    }
    _append_judgment(
        repo_root,
        call_site=call_site,
        inputs_hash=inputs_hash,
        response=fallback,
        outcome="fail_open_fallback",
        model=llm_id,
    )
    _print_response(fallback)
    return 0


def main(argv: Optional[list[str]] = None) -> int:
    cfg = parse_cli(list(sys.argv[1:] if argv is None else argv))
    return run(
        prompt_template=cfg.prompt_template,
        schema=cfg.schema,
        inputs=cfg.inputs,
        call_site=cfg.call_site,
        llm=cfg.llm,
    )
