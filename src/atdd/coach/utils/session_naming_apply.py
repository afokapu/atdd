from __future__ import annotations

import sys
from typing import Any

from atdd.coach.utils.multiplexer import MultiplexerError
from atdd.coach.utils.session_naming import target_grid_label

CANONICAL_SESSION_NAME_RULE_ID = "coach.orchestration.canonical-session-name"
LAYOUT_CONFORMANCE_RULE_ID = "coach.orchestration.layout-conformance"


def apply_canonical_name_and_layout(
    backend: Any,
    ref: str,
    canonical_name: str,
    surface_count: int,
) -> None:
    if not canonical_name:
        return
    try:
        rename = getattr(backend, "rename", None)
        if rename is not None:
            rename(ref, canonical_name)
        print(
            f"   rename target: {canonical_name} "
            f"({CANONICAL_SESSION_NAME_RULE_ID})"
        )
    except MultiplexerError as exc:
        print(
            f"⚠️  rename failed for {ref}: {exc} "
            f"({CANONICAL_SESSION_NAME_RULE_ID})",
            file=sys.stderr,
        )
    try:
        backend.send(ref, f"/rename {canonical_name}\n")
    except AttributeError as exc:
        print(
            f"⚠️  /rename injection unavailable for {ref}: {exc} "
            f"({CANONICAL_SESSION_NAME_RULE_ID})",
            file=sys.stderr,
        )
    except MultiplexerError as exc:
        print(
            f"⚠️  /rename injection failed for {ref}: {exc} "
            f"({CANONICAL_SESSION_NAME_RULE_ID})",
            file=sys.stderr,
        )
    layout = target_grid_label(surface_count)
    print(
        f"   layout target ({surface_count} surface[s]): {layout} "
        f"({LAYOUT_CONFORMANCE_RULE_ID})"
    )


__all__ = [
    "CANONICAL_SESSION_NAME_RULE_ID",
    "LAYOUT_CONFORMANCE_RULE_ID",
    "apply_canonical_name_and_layout",
]
