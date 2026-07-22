"""Wave orchestration for the train runner (docs/coach-decomposition.md §6.1, §7.1, Child 9).

This module is the new home of the multi-issue *wave* orchestration that used to
live in ``atdd.coach.commands.coach``: resolving the dependency-ordered wave plan,
driving each wave's members concurrently (now bounded by
``train.concurrency.max_parallel_issues``, §7.4), and the cold-start glue that
starts the observer, binds the drive seams onto the runner, and maps the per-issue
results into a ``ColdStartResult``. ``atdd.coach.commands.coach`` keeps
``@deprecated`` compatibility shims of the same names (``_resolve_waves``,
``_drive_wave_concurrently``, ``_execute_cold_start``) that delegate here through
the 3.87.0 soak (§11).

Layer discipline (§3.3): ``atdd.train.*`` MAY import ``atdd.coach.*`` (the policy +
handler layers), ``atdd.runtime.*`` and ``atdd.integrations.*`` and stdlib
(including ``threading``); it MUST NOT import ``atdd.cli`` or ``atdd.observer``.
The shared coach helpers (``ColdStartResult``, ``_drive_single_issue``,
``build_plan`` / ``compute_waves`` …) are referenced through the ``coach`` *module
object* (``_coach.<name>``) rather than bound by ``from ... import`` so that callers
monkeypatching ``coach.<name>`` (the existing coach test suite) keep working
unchanged during the migration. Those helpers move into the train/runtime layers in
Child 10 (§13.10).
"""
from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Callable, Optional

from atdd.coach.commands import coach as _coach

_logger = logging.getLogger("atdd.coach")


class _NullObserver:
    """No-op stand-in for the decommissioned coach observer (#1486).

    ``execute_cold_start`` drives its observer purely through ``start()`` /
    ``stop()``. The observer itself was coach sub-worker orchestration and left
    core; the injection seam is kept so a caller can still supply a real
    observer, but the default now observes nothing.
    """

    def __init__(self, runtime_dir: Path) -> None:
        self._runtime_dir = runtime_dir

    def start(self) -> None:
        return None

    def stop(self) -> None:
        return None

# Convenience re-bind for the immutable enum the bodies below reference.
Phase = _coach.Phase


def resolve_waves(cfg: "_coach.Config") -> list[list[int]]:
    """Resolve the dependency-ordered wave plan for a cold-start run.

    A multi-issue run derives waves from the dependency graph via
    :func:`compute_waves`; a single issue — or a graph that fails to build or
    resolve — collapses to one wave holding every requested issue number.
    """
    if len(cfg.issue_numbers) <= 1:
        return [cfg.issue_numbers]
    plan = _coach.build_plan(cfg.issue_numbers)
    if not plan:
        return [cfg.issue_numbers]
    try:
        return _coach.compute_waves(plan)
    except ValueError:
        _logger.warning(
            "coach cold-start: compute_waves could not order issues "
            "(cyclic or unresolvable dependency) — falling back to a single "
            "wave holding every requested issue",
            extra={
                "event": "coach.cold_start.wave_resolution_fallback",
                "issue_numbers": cfg.issue_numbers,
                "fallback": "single_wave",
            },
        )
        return [cfg.issue_numbers]


def drive_wave_concurrently(
    wave: list[int],
    drive_fn: Callable[[int], int],
    *,
    max_parallel: Optional[int] = None,
) -> dict[int, int]:
    """Drive every member of one wave concurrently, joining before returning.

    One worker thread per issue (issue #730) — ``drive_fn(issue_num)`` returns
    that member's rc. The join over all threads is the barrier that preserves
    between-wave dependency ordering: the next wave cannot start until every
    member of this one is terminal. Returns ``{issue_num: rc}``.

    Child 9 (#896): ``max_parallel`` caps how many members run at once
    (``train.concurrency.max_parallel_issues``, §7.4). When it is ``None`` or
    not less than the wave size, every member runs concurrently (the prior
    behavior); otherwise a semaphore admits at most ``max_parallel`` at a time
    while still launching one thread per member so the join barrier is unchanged.
    """
    results: dict[int, int] = {}
    results_lock = threading.Lock()
    gate = (
        threading.Semaphore(max_parallel)
        if max_parallel is not None and max_parallel > 0
        else None
    )

    def _worker(issue_num: int) -> None:
        if gate is not None:
            gate.acquire()
        try:
            rc = drive_fn(issue_num)
        finally:
            if gate is not None:
                gate.release()
        with results_lock:
            results[issue_num] = rc

    threads = [
        threading.Thread(
            target=_worker, args=(issue_num,),
            name=f"coach-issue-{issue_num}",
        )
        for issue_num in wave
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def _max_parallel_issues(runtime_dir: Path) -> Optional[int]:
    """Resolve ``train.concurrency.max_parallel_issues`` for this repo (§7.4).

    Best-effort: a missing/empty/malformed config falls back to the documented
    default (4). Never raises — concurrency capping is a throttle, not a gate.
    """
    try:
        from atdd.coach.utils.config import get_train_runner_config

        repo_root = _coach._repo_root_for(runtime_dir)
        cfg = get_train_runner_config(repo_root)
        value = (cfg.get("concurrency") or {}).get("max_parallel_issues")
        if isinstance(value, int) and value > 0:
            return value
    except Exception as exc:  # noqa: BLE001 — throttle config is best-effort
        _logger.warning(
            "coach cold-start: could not read max_parallel_issues; using default",
            extra={"error": str(exc), "error_type": type(exc).__name__},
        )
    return 4


def execute_cold_start(
    cfg: "_coach.Config",
    machines: list,
    runtime_dir: Path,
    *,
    _spawn_func: Optional[Callable] = None,
    _two_phase_func: Optional[Callable] = None,
    _injected_events: Optional[dict] = None,
    _max_loop_events: Optional[int] = None,
    _run_id_sink: Optional[list] = None,
    _observer_factory: Optional[Callable] = None,
    _max_parallel: Optional[int] = None,
    runner: Optional[object] = None,
    policy: Optional[object] = None,
) -> "_coach.ColdStartResult":
    """Wire and drive all issues through the full lifecycle (cold-start path).

    Waves run in dependency order (R6, issue #645): wave N+1 does not start
    until every member of wave N has reached a terminal state. Members WITHIN
    a single wave are driven concurrently — one worker thread per member, each
    with its own ``coach-run-*`` id and event loop — so the wave plan's
    ``Wave 0: #A,#B`` reflects real parallel execution (issue #730), now bounded
    by ``train.concurrency.max_parallel_issues`` (§7.4, Child 9).

    A BLOCKED member is surfaced in the returned :class:`ColdStartResult`
    without aborting siblings that already started (Decision #1). Returns a
    ``ColdStartResult`` carrying the aggregate ``rc`` and the BLOCKED issues.

    Issue #754 started exactly one MultiAgentObserver before driving waves and
    stopped it after all waves completed. #1486 decommissioned the observer
    (coach sub-worker orchestration left core), so the ``_observer_factory`` seam
    remains but defaults to :class:`_NullObserver` — waves are no longer observed.
    Callers that still want observation inject a factory.

    Child 8 (#895): when ``runner`` (a :class:`~atdd.train.runner_iface.TrainRunner`)
    and ``policy`` are supplied, each issue is driven through
    ``runner.start_issue`` — the TrainRunner seam (the production path always
    supplies a runner). The ``runner is None`` branch is a defensive fallback that
    drives the issue through the moved ``atdd.train.issue_runner.drive_single_issue``
    directly.
    """
    from atdd.train import issue_runner as _issue_runner

    factory = _observer_factory or _NullObserver
    coach_observer = factory(runtime_dir)
    coach_observer.start()

    waves = resolve_waves(cfg)
    max_parallel = _max_parallel if _max_parallel is not None else _max_parallel_issues(runtime_dir)
    machines_by_number = {sm.issue_number: sm for sm in machines}
    if runner is not None:
        # Drive the same StateMachine objects the wave bookkeeping inspects, and
        # thread the cold-start drive seams through the runner so start_issue
        # reproduces the previous _drive_single_issue call exactly.
        runner.bind_state_machines(machines_by_number)
        runner.bind_drive_context(
            cfg=cfg,
            runtime_dir=runtime_dir,
            spawn_func=_spawn_func,
            two_phase_func=_two_phase_func,
            max_loop_events=_max_loop_events,
            run_id_sink=_run_id_sink,
            injected_events=_injected_events,
        )

    def _drive_issue(issue_num: int) -> int:
        """Drive one issue INIT→terminal, returning its rc.

        A crashed driver yields rc 2 rather than propagating, so one member's
        failure can never abort its siblings (issue #730, Decision #1).
        """
        sm = machines_by_number.get(issue_num)
        if sm is None:
            return 0
        try:
            if runner is not None:
                run_id = runner.start_issue(issue_num, policy=policy)
                return runner.rc_for(run_id)
            return _issue_runner.drive_single_issue(
                cfg, sm, runtime_dir,
                _spawn_func=_spawn_func,
                _two_phase_func=_two_phase_func,
                _injected_events=(_injected_events or {}).get(issue_num),
                _max_loop_events=_max_loop_events,
                _run_id_sink=_run_id_sink,
            )
        except Exception:  # noqa: BLE001 — a crashed driver must not abort siblings
            _logger.exception(
                "coach cold-start: issue driver raised",
                extra={"issue": issue_num},
            )
            return 2

    aggregate_rc = 0
    blocked: list[int] = []
    try:
        for wave in waves:
            wave_results = drive_wave_concurrently(
                wave, _drive_issue, max_parallel=max_parallel
            )
            # Aggregate this wave's outcomes — a BLOCKED member is recorded, not
            # fatal: siblings already running are left to finish.
            for issue_num, rc in wave_results.items():
                if rc != 0 and aggregate_rc == 0:
                    aggregate_rc = rc
                sm = machines_by_number.get(issue_num)
                if sm is not None and sm.phase == Phase.BLOCKED:
                    blocked.append(issue_num)
    finally:
        coach_observer.stop()

    return _coach.ColdStartResult(rc=aggregate_rc, blocked=blocked)


__all__ = [
    "resolve_waves",
    "drive_wave_concurrently",
    "execute_cold_start",
]
