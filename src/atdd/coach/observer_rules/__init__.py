# URN: component:observe-and-correct:observer-runtime-and-rules:observer_rules:backend:application
# Runtime: python
# Purpose: Observer detection rules (spec §8.3) and their shared detectors.

"""Observer rule modules for the coach observer (spec §8.3).

Each module exposes:

  ``predicate(ctx)``  — pure boolean drift / violation detector
  ``build_rule()``    — factory returning an :class:`ObserverRule` ready
                        to register with :class:`RuleRegistry`
  (optional) ``apply_correction(ctx, **context)`` — side-effect path that
                        invokes a :mod:`detectors` corrector (rename a
                        surface, log layout target, etc.)

The shared classification + correction primitives live in
:mod:`atdd.coach.observer_rules.detectors`.

Rule IDs declared in ``src/atdd/coach/conventions/observer.convention.yaml``.
"""

__all__: list[str] = []
