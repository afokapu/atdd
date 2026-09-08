# Phase: SMOKE
# Layer: integration
# Assertion: behavioral
"""#1815 — a logging call must not be able to raise on the message it is reporting.

``logging`` refuses to let ``extra=`` overwrite a built-in ``LogRecord``
attribute. It does not warn or drop the key: ``Logger.makeRecord`` raises
``KeyError: "Attempt to overwrite 'name' in LogRecord"``. The raise happens at
CALL time and only when the level is enabled, so a reserved key sits inert
through every default-level run and fires the first time somebody raises the log
level — which is to say, the first time somebody is debugging.

That is not hypothetical here. ``state/db.py`` logged
``extra={"version": ..., "name": migration.name}`` on both the applied and the
failed branch of the migration runner. On a fresh State Store, with INFO enabled,
the applied branch raised **inside** the store-open path that the #1602 smoke
attestation writer calls. The writer's fail-closed posture swallowed it and
reported::

    smoke attestation: could not record 2 run(s); the SMOKE->REFACTOR gate will
    read this as 'smoke did not run': "Attempt to overwrite 'name' in LogRecord"

The real reason the run recorded nothing was different and much simpler — a CI
checkout has no registered work item — so the reserved key did not merely fail to
log. It REPLACED a correct diagnostic with a misleading one, in the one
configuration an operator would reach for to investigate. The failed branch is
worse still: it would raise while reporting that a migration failed, losing the
original error entirely.

Scanned statically over the package, so a call on a path no test exercises is
still caught — which is the whole point, since the offending line ran only under
a log level no test sets.
"""
from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import List, Tuple

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = REPO_ROOT / "src" / "atdd"

#: Attributes `logging.Logger.makeRecord` refuses to let `extra=` overwrite.
#: Derived from a real record rather than hardcoded, so a future Python that adds
#: an attribute is covered without anyone remembering to update a list here.
RESERVED = frozenset(
    vars(
        logging.LogRecord(
            name="probe", level=logging.INFO, pathname=__file__, lineno=1,
            msg="", args=(), exc_info=None,
        )
    )
) | {"message", "asctime"}

#: Callables whose `extra=` keyword is the logging one.
_LOG_METHODS = frozenset(
    {"debug", "info", "warning", "warn", "error", "exception", "critical", "log"}
)


def _offending_calls(source: str) -> List[Tuple[int, str]]:
    """`(line, key)` for every logging call passing a reserved key in `extra=`."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr in _LOG_METHODS):
            continue
        for keyword in node.keywords:
            if keyword.arg != "extra" or not isinstance(keyword.value, ast.Dict):
                continue
            for key in keyword.value.keys:
                if isinstance(key, ast.Constant) and key.value in RESERVED:
                    found.append((node.lineno, str(key.value)))
    return found


def test_the_reserved_set_is_not_empty() -> None:
    """Guard the guard: an empty reserved set would pass every file vacuously."""
    assert {"name", "args", "module", "lineno"} <= RESERVED, sorted(RESERVED)


def test_makerecord_really_does_raise_on_a_reserved_key() -> None:
    """The premise, asserted rather than assumed — it is why this file exists."""
    logger = logging.getLogger("atdd.test.reserved-probe")
    logger.setLevel(logging.INFO)
    with pytest.raises(KeyError):
        logger.makeRecord(
            "n", logging.INFO, __file__, 1, "m", (), None, extra={"name": "x"}
        )


def test_no_logging_call_in_the_package_uses_a_reserved_logrecord_key() -> None:
    offenders: List[str] = []
    scanned = 0
    for path in sorted(PACKAGE.rglob("*.py")):
        scanned += 1
        for line, key in _offending_calls(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(f"  {path.relative_to(REPO_ROOT)}:{line} — extra[{key!r}]")

    assert scanned > 100, f"only {scanned} files scanned — the walk is broken"
    assert not offenders, (
        "these logging calls pass a reserved LogRecord attribute in `extra=`, so the "
        "call raises KeyError once its level is enabled — silently inert until someone "
        "turns logging up to debug a problem, and then replacing that problem's "
        "diagnostic with a complaint about logging:\n" + "\n".join(offenders)
    )
