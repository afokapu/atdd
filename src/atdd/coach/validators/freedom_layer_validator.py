"""freedom_layer_validator — the flipped freedom-set safety check (WMBT E032, #1062).

This replaces the E013-era "Bash absent" check (a Python-specific inspection of
``ADAPTER_REGISTRY.allowed_tools``) with a data-only invariant over the convention
``spawn_time.freedom_layer`` declaration:

  * every ``allowed_bash`` entry is tightly scoped — ``Bash(<cmd>:*)`` — never bare
    ``Bash``, ``Bash(*)``, or ``Bash(:*)`` (a loose prefix can be chained, e.g.
    ``pytest && rm -rf``);
  * no ``allowed_bash`` entry's inner command appears in ``forbidden_bash`` (the
    destructive/outward deny-list).

The check consumes plain ``freedom_layer`` data (a dict), so the same rule holds for
any stack's allow-list (``Bash(go test:*)``, ``Bash(npm test:*)``, …) — it does no
Python source/AST inspection. The data varies per stack (#1035); the rule is constant.
"""
from __future__ import annotations

import re
from typing import List, Mapping

# A tightly-scoped Bash entry: Bash(<cmd>:*) with a non-empty inner command that
# contains no parentheses. Rejects bare ``Bash``, ``Bash(*)``, ``Bash(:*)``.
_SCOPED_RE = re.compile(r"^Bash\((?P<cmd>[^()]+):\*\)$")


def check_freedom_layer_allowlist_safety(freedom_layer: Mapping) -> List[str]:
    """Return a list of violation strings for ``freedom_layer`` (empty == clean).

    ``freedom_layer`` is the convention ``spawn_time.freedom_layer`` data: a mapping
    carrying ``allowed_bash`` (scoped safe Bash prefixes) and ``forbidden_bash``
    (destructive/outward commands that must never be pre-authorized). Pure data in,
    list of human-readable violations out — language-agnostic.
    """
    violations: List[str] = []
    allowed_bash = list(freedom_layer.get("allowed_bash") or [])
    forbidden = list(freedom_layer.get("forbidden_bash") or [])

    for entry in allowed_bash:
        match = _SCOPED_RE.match(entry)
        if match is None:
            violations.append(
                f"unscoped/over-broad Bash entry {entry!r}: every allowed_bash entry "
                f"must be tightly scoped Bash(<cmd>:*) (never bare Bash, Bash(*), or "
                f"Bash(:*))"
            )
            continue
        inner = match.group("cmd")
        for bad in forbidden:
            # A forbidden command leaks if it is the exact inner command or its
            # prefix (prefix-match injection guard: 'git push' must catch
            # 'git push origin', etc.).
            if inner == bad or inner.startswith(bad + " "):
                violations.append(
                    f"forbidden command {bad!r} present in allowed_bash entry "
                    f"{entry!r}: destructive/outward commands must never be "
                    f"pre-authorized"
                )

    return violations
