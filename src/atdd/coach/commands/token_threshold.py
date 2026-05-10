"""Coach observer: token-threshold alerting (issue #507 / spec §8.3).

Absorbs babysit's token-count alerting machinery — `load_token_alert_threshold`,
`read_token_count`, `check_token_threshold` — into a coach module so the
observer's rule `06-token-threshold` can drive the alert from the L1
evaluation loop instead of the babysit polling loop. Behavior parity with
babysit is preserved (same firing decision for the same inputs); the
default 400k threshold is preserved per spec §10.

Spec references:
    §0.2  Absorption inventory — token alerting
    §8.3  Rule 06 (token threshold) — correction text
    §10   Configuration key `coach.token_alert_threshold` (default 400000)
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from atdd.coach.utils.config import load_atdd_config


# =============================================================================
# Default threshold (spec §10)
# =============================================================================
# 400k leaves ~200k headroom under the typical 600k effective cap, giving the
# worker enough budget to react to the alert (run /compact, optionally /clear
# and `atdd session-template <N> --from-checkpoint`).
DEFAULT_TOKEN_ALERT_THRESHOLD: int = 400_000


# Configuration namespaces, in resolution order. `coach.*` is the spec §10
# canonical key; `babysit.*` is honored as a legacy fallback so pre-absorption
# `.atdd/config.yaml` files keep working through the deprecation window owned
# by #P6.
_CONFIG_NAMESPACES: tuple[str, ...] = ("coach", "babysit")
_CONFIG_KEY: str = "token_alert_threshold"


def load_token_alert_threshold(*, repo_root: Optional[Path] = None) -> int:
    """Resolve the token-alert threshold from `.atdd/config.yaml` or fall back
    to the documented default.

    Resolution order (issue #507):
        1. `coach.token_alert_threshold` (spec §10 canonical key)
        2. `babysit.token_alert_threshold` (legacy, pre-absorption)
        3. ``DEFAULT_TOKEN_ALERT_THRESHOLD`` (400_000)

    A malformed or unreadable config silently falls back to the default —
    parity with babysit's pre-absorption behavior.
    """
    base = Path(repo_root) if repo_root is not None else Path.cwd()
    try:
        config = load_atdd_config(base)
    except Exception:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # parity with babysit's silent fallback for malformed config
        return DEFAULT_TOKEN_ALERT_THRESHOLD
    if not isinstance(config, dict):
        return DEFAULT_TOKEN_ALERT_THRESHOLD
    for namespace in _CONFIG_NAMESPACES:
        section = config.get(namespace)
        if not isinstance(section, dict):
            continue
        value = section.get(_CONFIG_KEY)
        if isinstance(value, int) and not isinstance(value, bool) and value > 0:
            return value
    return DEFAULT_TOKEN_ALERT_THRESHOLD


def read_token_count(
    *,
    runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
    timeout: float = 5.0,
) -> Optional[int]:
    """Best-effort token count via `claude --print-context-status`.

    Returns ``None`` when the binary is missing, the call errors, or the
    output is not parseable JSON. Callers MUST treat ``None`` as "unknown" —
    the rule's predicate uses None as a no-fire signal (parity with babysit
    where the dashboard renders this as ``—``).

    Decision 6 (issue #378, preserved by absorption): the source mechanism
    is `claude --print-context-status`. A future revision can swap in a
    per-surface multiplexer command without changing the alert logic.

    Parameters:
        runner: Injection point for tests — defaults to ``subprocess.run``.
        timeout: Subprocess timeout in seconds.
    """
    run = runner or subprocess.run
    try:
        result = run(
            ["claude", "--print-context-status"],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except (FileNotFoundError, subprocess.SubprocessError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # parity with babysit: best-effort, missing binary or call error → None
        return None
    if getattr(result, "returncode", 1) != 0:
        return None
    stdout = getattr(result, "stdout", "")
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, TypeError):  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-01  # parity with babysit: unrecognized stdout shape → None
        return None
    if not isinstance(payload, dict):
        return None
    for key in ("context_used_tokens", "tokens_used", "tokens"):
        value = payload.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return None


def check_token_threshold(
    *, token_count: Optional[int], threshold: int
) -> bool:
    """Return True when the token count meets or exceeds the threshold.

    Parity with babysit (issue #507 absorption):
        - ``None`` token_count   → False (unknown ⇒ no alert)
        - ``count <  threshold`` → False
        - ``count >= threshold`` → True (firing at exactly threshold matches
          babysit's `>=` semantics — see test_check_alerts_at_exactly_threshold).
    """
    if token_count is None:
        return False
    return token_count >= threshold
