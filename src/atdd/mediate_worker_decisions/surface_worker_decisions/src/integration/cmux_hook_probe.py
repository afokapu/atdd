"""cmux_hook_probe — HookPresenceProbe over the real cmux launch environment (WMBT L004).

The cmux Claude wrapper injects its PermissionRequest->'cmux hooks feed' hook only
when the worker runs under the wrapper with CMUX_SURFACE_ID set and a live cmux
socket. This probe reads that environment so a non-publishing launch is detected
loudly instead of looking falsely healthy.
"""
from __future__ import annotations

import logging
import os
import stat
from typing import Mapping, Optional

from atdd.mediate_worker_decisions.surface_worker_decisions.src.application.ports import (
    HookPresence,
)

_log = logging.getLogger(__name__)


class CmuxHookProbe:
    """Confirms the wrapper hook path from the launch environment."""

    def __init__(self, env: Optional[Mapping[str, str]] = None) -> None:
        self._env = env if env is not None else os.environ

    def evaluate(self) -> HookPresence:
        """Active iff CMUX_SURFACE_ID is set and the cmux socket path is a live socket.

        The cmux Claude wrapper injects its PermissionRequest->feed hook only when
        the worker runs under it with CMUX_SURFACE_ID set and a reachable socket. We
        check both preconditions and name the first that is missing.
        """
        surface_id = self._env.get("CMUX_SURFACE_ID")
        if not surface_id:
            return HookPresence(
                active=False,
                reason="CMUX_SURFACE_ID not set (worker is not running under a cmux surface)",
            )
        socket_path = self._env.get("CMUX_SOCKET_PATH")
        if not socket_path:
            return HookPresence(
                active=False, reason="CMUX_SOCKET_PATH not set (no cmux socket to publish to)"
            )
        try:
            mode = os.stat(socket_path).st_mode
        except OSError as exc:
            _log.debug(
                "cmux socket not reachable",
                extra={"socket_path": socket_path, "error": str(exc)},
            )
            return HookPresence(
                active=False,
                reason=f"CMUX_SOCKET_PATH {socket_path!r} not reachable: {exc}",
            )
        if not stat.S_ISSOCK(mode):
            return HookPresence(
                active=False, reason=f"CMUX_SOCKET_PATH {socket_path!r} is not a socket"
            )
        return HookPresence(active=True, reason="")
