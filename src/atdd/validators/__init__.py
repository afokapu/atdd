"""``atdd.validators`` — validation layer (docs/coach-decomposition.md §4.11).

Validators run checks against repo state and emit :class:`ValidatorReport` rows;
they do not decide what to do with violations (that is Coach-core's job, §3.2).

The existing per-persona validator suites stay where they are
(``src/atdd/{planner,tester,coder,coach}/validators/``); this top-level package
holds the *emission* infrastructure they call.

``ValidatorReport`` is *defined* in the pure-policy module ``atdd.coach.core.types``
(so the dependency direction points inward, §4.2). It is re-exported here as the
stable import location for validator emission::

    from atdd.validators import ValidatorReport, emit_reports
"""
from __future__ import annotations

from atdd.coach.core.types import ValidatorReport
from atdd.validators.emit import emit_reports

__all__ = ["ValidatorReport", "emit_reports"]
