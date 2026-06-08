"""LLM-coach adapter (provider-pluggable), one-shot and decide-only.

Implements the feed ``Coach`` port (``mediate(request) -> Verdict``). When the
request carries a modular ``document`` the adapter renders EVERY block and asks
the configured LLM provider for a structured per-block answer (WMBT E006): one
option id for a single_choice, a LIST of ids for a multi_choice, text for
free_text, approve/deny for confirm — never just the first block. The per-block
answer is parsed back into a ``DecisionAnswer`` (each choice answer carried as
``Option`` objects so the reply side has labels and the contract side has ids),
and each block's answer is constrained to that block's own options. A legacy
single-question request (no document) falls back to the original render ->
pick-one-label path.

Provider-pluggable by construction: the worker/format side of the wagon is
already agent-agnostic; ``LlmCoach`` is the pluggable DECIDER seam.
``provider='claude'`` (the default and only implementation today) invokes
``claude -p``. Adding a future provider is a single entry in
``_PROVIDER_CLI_FACTORIES`` — no other code changes — but codex/gemini are
intentionally NOT implemented now; an unknown provider raises
``UnsupportedCoachProvider`` rather than silently falling back.

Decides AS A COACH (WMBT E011): the coach convention + operating protocol (the
canonical ATDD phase machine, resolved from the repo) is loaded once and carried
into the provider CLI as an appended system prompt — for claude via
``--append-system-prompt``. The CLI seam takes a ``system`` keyword so the SAME
coach context flows to any provider, not just claude. A blank ``claude -p`` is
never issued; this is a strict quality upgrade with no behavior removed.

Decide-only by design: the dangerous-action safety gate already runs *ahead* of
the coach in ``FeedRunnerUseCase`` (WMBT C003/C005), so a dangerous tool use /
dangerous block never reaches this adapter. ``LlmCoach`` therefore only chooses
among the offered options; it does not re-classify safety.
"""
from __future__ import annotations

import json
import logging
import subprocess
import uuid
from datetime import datetime, timezone
from typing import Callable, List, Optional

from atdd.mediate_worker_decisions.bridge_cmux_feed.src.integration.coach_context import (
    load_coach_context,
)
from atdd.mediate_worker_decisions.mediate_decision.src.domain.verdict import (
    AUTO_APPLY,
    SOURCE_COACH,
    Verdict,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_document import (
    APPROVE,
    CONFIRM,
    DENY,
    FREE_TEXT,
    MULTI_CHOICE,
    SINGLE_CHOICE,
    Block,
    BlockAnswer,
    DecisionAnswer,
    DecisionDocument,
)
from atdd.mediate_worker_decisions.sense_decision.src.domain.decision_request import (
    DecisionRequest,
)

_log = logging.getLogger("atdd.feed_daemon")

_COACH_TIMEOUT = 90.0
DEFAULT_PROVIDER = "claude"

# A provider CLI is a callable ``(prompt, *, system, timeout) -> str`` returning
# stdout. ``system`` carries the coach convention / operating protocol (E011) so
# the decider decides as a coach; each provider decides how to apply it (claude
# appends it via ``--append-system-prompt``).
CoachCli = Callable[..., str]


class UnsupportedCoachProvider(ValueError):
    """Raised when an LlmCoach is asked for a provider with no CLI factory."""


class CoachInvocationError(RuntimeError):
    """Raised when the provider CLI (e.g. ``claude -p``) fails to produce output.

    Surfaced (not swallowed) so the daemon decide loop escalates the decision to a
    human and loud-logs it, instead of turning a dead ``claude -p`` into an empty
    silent verdict — the #1007 failure mode in the detached, no-TTY daemon context.
    """


def _default_id_factory() -> str:
    return str(uuid.uuid4())


def _default_ts_factory() -> str:
    return datetime.now(timezone.utc).isoformat()


def _claude_cli_factory(model: Optional[str]) -> CoachCli:
    """Build the ``claude -p`` CLI (optionally pinned to ``--model``).

    When ``system`` is supplied (the coach convention / operating protocol, E011)
    it is appended to the call via ``--append-system-prompt`` so the decider
    decides as a coach rather than a blank LLM.
    """

    def run(prompt: str, *, system: Optional[str] = None, timeout: float) -> str:
        cmd = ["claude", "-p", prompt]
        if model:
            cmd += ["--model", model]
        if system:
            cmd += ["--append-system-prompt", system]
        # Explicit stdin=DEVNULL: the autonomous daemon runs detached with no TTY, so
        # claude -p must not inherit (or block on) the daemon's stdin (#1007).
        completed = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
        if completed.returncode != 0:
            # Surface the failure so the daemon escalates rather than silently
            # producing an empty (first-option) verdict from no output.
            raise CoachInvocationError(
                f"claude -p exited {completed.returncode}: "
                f"{(completed.stderr or '').strip()[:500]}"
            )
        return completed.stdout

    return run


# provider -> CLI factory. The ONLY implementation today is claude; a future
# provider is a single new entry here (the seam), nothing else.
_PROVIDER_CLI_FACTORIES = {
    "claude": _claude_cli_factory,
}


def resolve_provider_cli(provider: str, model: Optional[str]) -> CoachCli:
    """Resolve a provider name to its CLI, or refuse an unknown provider."""
    try:
        factory = _PROVIDER_CLI_FACTORIES[provider]
    except KeyError:
        supported = ", ".join(sorted(_PROVIDER_CLI_FACTORIES))
        raise UnsupportedCoachProvider(
            f"unsupported coach provider {provider!r}; supported: {supported}"
        )
    return factory(model)


class LlmCoach:
    """A real coach: renders the request and asks an LLM provider to answer it.

    ``provider`` selects the decider backend (default ``claude``); ``model``
    optionally pins a model. ``cli`` / id / ts factories are injectable so the
    adapter is unit-testable without shelling out (the hermetic tests inject a
    fake cli); when ``cli`` is omitted it is resolved from ``provider``/``model``.

    ``coach_context`` is the coach convention / operating protocol carried into
    every provider call so the decider decides as a coach (E011). When omitted it
    is loaded once (lazily, on first decision) from the repo via
    ``context_loader``; tests inject a known string to assert it reaches the args.
    """

    def __init__(
        self,
        *,
        provider: str = DEFAULT_PROVIDER,
        model: Optional[str] = None,
        cli: Optional[CoachCli] = None,
        coach_context: Optional[str] = None,
        context_loader: Callable[[], str] = load_coach_context,
        id_factory: Callable[[], str] = _default_id_factory,
        ts_factory: Callable[[], str] = _default_ts_factory,
        timeout: float = _COACH_TIMEOUT,
    ) -> None:
        self._provider = provider
        self._model = model
        self._cli = cli if cli is not None else resolve_provider_cli(provider, model)
        # Lazily resolved: None means "load the coach convention on first decision"
        # so unit tests that don't inject context don't pay a filesystem read at
        # construction (and an injected string short-circuits the load entirely).
        self._coach_context = coach_context
        self._context_loader = context_loader
        self._id = id_factory
        self._ts = ts_factory
        self._timeout = timeout

    def _system_prompt(self) -> str:
        """The coach convention / operating protocol carried to the decider (E011)."""
        if self._coach_context is None:
            self._coach_context = self._context_loader()
        return self._coach_context

    def mediate(self, request: DecisionRequest) -> Verdict:
        if request.document is not None:
            return self._mediate_document(request, request.document)
        return self._mediate_single(request)

    # -- document path (WMBT E006) ----------------------------------------- #
    def _mediate_document(
        self, request: DecisionRequest, document: DecisionDocument
    ) -> Verdict:
        prompt = _render_document_prompt(document)
        output = self._cli(prompt, system=self._system_prompt(), timeout=self._timeout)
        answer = _parse_document_answer(output, document)
        return Verdict(
            verdict_id=self._id(),
            request_id=request.request_id,
            decided_at=self._ts(),
            disposition=AUTO_APPLY,
            source=SOURCE_COACH,
            selected_option_id=_first_block_label(answer),
            reason=f"coach decided the whole document via {self._provider}",
            answer=answer,
        )

    # -- legacy single-question path --------------------------------------- #
    def _mediate_single(self, request: DecisionRequest) -> Verdict:
        prompt = _render_decision_prompt(request)
        output = self._cli(prompt, system=self._system_prompt(), timeout=self._timeout)
        label = _parse_selection(output, request)
        return Verdict(
            verdict_id=self._id(),
            request_id=request.request_id,
            decided_at=self._ts(),
            disposition=AUTO_APPLY,
            source=SOURCE_COACH,
            selected_option_id=label,
            reason=f"coach decided via {self._provider}",
        )


# --------------------------------------------------------------------------- #
# document rendering + parsing                                                 #
# --------------------------------------------------------------------------- #
def _render_document_prompt(document: DecisionDocument) -> str:
    lines = [
        "You are answering a decision composed of several blocks. Answer EVERY "
        "block. Reply with ONLY a JSON object of the form:",
        '{"answers": [{"block_id": "<id>", "selected_ids": ["<id>", ...]}]}',
        "Use selected_ids (one id for single_choice, one-or-more for "
        "multi_choice), text for free_text, or decision (approve/deny) for "
        "confirm. Do not omit any block.",
        "",
        "Blocks:",
    ]
    for block in document.leaf_blocks():
        lines.append(f"- block_id={block.block_id} kind={block.kind}: {block.prompt}")
        for opt in block.options:
            lines.append(f"    [{opt.id}] {opt.label}")
    return "\n".join(lines)


def _parse_document_answer(output: str, document: DecisionDocument) -> DecisionAnswer:
    entries = _parse_answer_entries(output)
    by_id = {str(e.get("block_id", "")): e for e in entries if isinstance(e, dict)}

    answers: List[BlockAnswer] = []
    for block in document.leaf_blocks():
        entry = by_id.get(block.block_id, {})
        answers.append(_block_answer(block, entry))
    return DecisionAnswer(answers=tuple(answers))


def _parse_answer_entries(output: str) -> list:
    """Tolerantly extract the ``answers`` list from the coach's reply."""
    text = _strip_code_fence(output or "")
    try:
        payload = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        # Degrade observably: an unparseable coach reply yields no answers (the
        # downstream blocks resolve to empty selections) — never silently. The
        # parse failure is loudly surfaced so the operator sees a malformed coach
        # response rather than a wrongly-answered worker.
        _log.warning(
            "coach reply was not valid JSON; document answers will be empty",
            extra={"parse_error": str(exc), "reply_len": len(text)},
        )
        return []
    if isinstance(payload, dict):
        answers = payload.get("answers", [])
        return answers if isinstance(answers, list) else []
    if isinstance(payload, list):
        return payload
    return []


def _block_answer(block: Block, entry: dict) -> BlockAnswer:
    if block.kind == FREE_TEXT:
        return BlockAnswer(block.block_id, block.kind, text=str(entry.get("text", "")))
    if block.kind == CONFIRM:
        return BlockAnswer(
            block.block_id, block.kind, decision=_confirm_decision(entry)
        )
    # single_choice / multi_choice: constrain to THIS block's options (E006-UNIT-002)
    selected = _constrained_options(block, entry)
    if block.kind == SINGLE_CHOICE:
        selected = selected[:1]
    return BlockAnswer(block.block_id, block.kind, selected=selected)


def _constrained_options(block: Block, entry: dict) -> tuple:
    raw_ids = entry.get("selected_ids")
    if raw_ids is None:
        raw_ids = entry.get("selected", [])
    chosen = {str(i) for i in raw_ids} if isinstance(raw_ids, list) else set()
    # preserve the block's own option order; drop any id not in this block
    return tuple(opt for opt in block.options if opt.id in chosen)


def _confirm_decision(entry: dict) -> Optional[str]:
    decision = str(entry.get("decision", "")).strip().lower()
    if decision in (APPROVE, DENY):
        return decision
    return None


def _first_block_label(answer: DecisionAnswer) -> Optional[str]:
    """Back-compat single-selection mirror: the first choice block's first label."""
    for block_answer in answer.answers:
        if block_answer.selected:
            return block_answer.selected[0].label
    return None


def _strip_code_fence(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        # drop the opening fence line and the trailing fence
        body = stripped.split("\n", 1)[1] if "\n" in stripped else ""
        if body.rstrip().endswith("```"):
            body = body.rstrip()[: -len("```")]
        return body.strip()
    return stripped


# --------------------------------------------------------------------------- #
# legacy single-question rendering + parsing                                   #
# --------------------------------------------------------------------------- #
def _render_decision_prompt(request: DecisionRequest) -> str:
    lines = [request.prompt.question, "", "Options:"]
    lines += [f"- {o.label}" for o in request.prompt.options]
    lines += ["", "Reply with ONLY the exact label of the best option, nothing else."]
    return "\n".join(lines)


def _parse_selection(output: str, request: DecisionRequest) -> str:
    """Pick the option whose label appears in the coach's reply (else the first)."""
    low = (output or "").lower()
    for opt in request.prompt.options:
        if opt.label.lower() in low:
            return opt.label
    return request.prompt.options[0].label if request.prompt.options else ""
