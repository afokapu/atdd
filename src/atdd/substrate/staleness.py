# URN: component:code:substrate:StalenessCheck:backend:src
# Runtime: python
# Purpose: report vendored packages a registry has moved past, without applying anything (#1878).
"""Is a vendored package behind what its registry publishes?

`substrate add` vendors a copy and records the version; nothing pulls afterwards.
Core sat on `train-interlocking-enforcement/0.1.0` — already split by persona and
migrated off `category_digit` upstream — and kept enforcing it. Each re-pin since
(#1842, #1854, #1871) happened because a human noticed.

REPORT, NEVER APPLY. A version bump in that hub means enforced behaviour changed
in a way that flips verdicts: 0.4.0 makes a half-migrated consumer fail where it
previously passed, deliberately. Auto-applying would break a consumer's CI from
someone else's push, with no local change and nothing in the diff to explain it.
The lock exists to stop exactly that.

AND AN UNREACHABLE REGISTRY IS NOT "UP TO DATE". That is the whole discipline
here: a staleness check that says "fine" when it could not look is the same defect
as a green badge over a suite that never ran. This module reuses the verdict
vocabulary core already ships (`coach.documentation.verdict`) rather than
inventing a second one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional, Sequence

from atdd.coach.documentation import verdict as _verdict

#: Re-exported so callers read one vocabulary, not two.
PASS = _verdict.PASS
COULD_NOT_CHECK = _verdict.COULD_NOT_CHECK
NOT_APPLICABLE = _verdict.NOT_APPLICABLE


@dataclass(frozen=True)
class Staleness:
    """One installed package judged against what a registry publishes."""

    package_id: str
    installed_version: str
    latest_version: Optional[str]
    verdict: str
    detail: str

    @property
    def is_stale(self) -> bool:
        """A newer release exists. False for COULD_NOT_CHECK — see `blocks`."""
        return self.verdict == PASS and self.latest_version is not None and (
            self.installed_version != self.latest_version
        )


def _entry_for(package_id: str, entries: Sequence) -> Optional[object]:
    for e in entries:
        if getattr(e, "id", None) == package_id:
            return e
    return None


def evaluate(installed: Iterable[dict], entries: Optional[Sequence]) -> list[Staleness]:
    """Judge each installed artifact against the registry entries.

    ``entries is None`` means the registry could not be READ — unreachable, or a
    schema the reader refuses. Every package then reports COULD_NOT_CHECK. It is
    deliberately not an empty list: `[]` is a registry that answered and offers
    nothing, which is a different fact and reports NOT_APPLICABLE per package.
    """
    out: list[Staleness] = []
    for art in installed:
        pid = str(art.get("id") or "")
        version = str(art.get("version") or "")
        if not pid:
            continue
        if entries is None:
            out.append(Staleness(
                pid, version, None, COULD_NOT_CHECK,
                "the registry could not be read, so staleness was NOT established; "
                "this is not 'up to date'",
            ))
            continue
        entry = _entry_for(pid, entries)
        if entry is None:
            out.append(Staleness(
                pid, version, None, NOT_APPLICABLE,
                "no registry entry publishes this package, so there is nothing to be "
                "behind (a locally-admitted package is not stale)",
            ))
            continue
        latest = getattr(entry, "latest_version", None)
        if not latest:
            out.append(Staleness(
                pid, version, None, COULD_NOT_CHECK,
                "the registry entry publishes no latest_version, so staleness could "
                "not be established",
            ))
            continue
        if version != latest:
            out.append(Staleness(
                pid, version, latest, PASS,
                f"installed {version}, registry publishes {latest}",
            ))
        else:
            out.append(Staleness(pid, version, latest, PASS, f"up to date at {latest}"))
    return out


def blocks(results: Iterable[Staleness]) -> bool:
    """True when any result is one this check could not establish.

    Staleness itself does NOT block — being behind is information, and applying is
    the operator's call. An unestablished verdict does, because silence there is
    indistinguishable from a clean result.
    """
    return any(r.verdict == COULD_NOT_CHECK for r in results)


def summarize(results: Sequence[Staleness]) -> str:
    """One line per package, plus a verdict that never hides a could-not-check."""
    if not results:
        return "substrate is empty (no admitted artifacts to check)"
    lines = []
    for r in sorted(results, key=lambda r: r.package_id):
        mark = {PASS: "stale" if r.is_stale else "ok",
                COULD_NOT_CHECK: "COULD_NOT_CHECK",
                NOT_APPLICABLE: "n/a"}[r.verdict]
        lines.append(f"  [{mark}] {r.package_id}  {r.detail}")
    stale = sum(1 for r in results if r.is_stale)
    unknown = sum(1 for r in results if r.verdict == COULD_NOT_CHECK)
    if unknown:
        lines.append(
            f"verdict: COULD_NOT_CHECK — {unknown} package(s) could not be judged. "
            f"This is NOT a clean result."
        )
    elif stale:
        lines.append(f"verdict: {stale} package(s) behind the registry. Apply deliberately: atdd substrate add <id>")
    else:
        lines.append("verdict: every admitted package matches what its registry publishes")
    return "\n".join(lines)
