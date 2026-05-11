"""Subprocess-based LLM client that delegates to the local claude CLI.

This shim avoids API-key management inside atdd: the claude binary handles
auth. The prompt is written to stdin; stdout is parsed as JSON (stripping
any markdown code-fence wrapper the CLI may add).
"""
from __future__ import annotations

import json
import re
import subprocess
from typing import Any

from atdd.coach.commands.judge import LLMUnavailable


def _extract_json(text: str) -> Any:
    """Parse JSON from possibly markdown-wrapped CLI output."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
        pass
    m = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1).strip())
        except json.JSONDecodeError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            pass
    m = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            pass
    raise LLMUnavailable(f"no JSON found in response (first 200 chars): {text[:200]!r}")


class ClaudeSubprocessClient:
    """Invoke `claude -p` with a JSON-requesting prompt, return parsed JSON."""

    def __init__(self, *, claude_bin: str, model_id: str) -> None:
        self._claude_bin = claude_bin
        self._model_id = model_id

    def invoke(self, prompt: str) -> Any:
        json_prompt = (
            f"{prompt}\n\n"
            "Return ONLY valid JSON matching the schema above. "
            "No explanation, no markdown, no prose."
        )
        try:
            result = subprocess.run(
                [self._claude_bin, "-p", "--model", self._model_id],
                input=json_prompt,
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            raise LLMUnavailable(f"{self._model_id} subprocess timed out") from exc
        except OSError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01
            raise LLMUnavailable(f"{self._model_id} subprocess failed to start: {exc}") from exc

        if result.returncode != 0:
            raise LLMUnavailable(
                f"{self._model_id} exited {result.returncode}: {result.stderr[:200]}"
            )
        return _extract_json(result.stdout)
