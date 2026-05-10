# URN: component:observe-and-correct:observer-runtime-and-rules:observer_rules:backend:application
# Runtime: python
# Purpose: Observer detection rules absorbed verbatim from babysit per spec §0.2.

"""Observer rule modules for coach v9 (spec §8.3).

Each module exposes:

  ``predicate(ctx)``  — pure boolean drift / violation detector
  ``build_rule()``    — factory returning an :class:`ObserverRule` ready
                        to register with :class:`RuleRegistry`
  (optional) ``apply_correction(ctx, **context)`` — side-effect path that
                        invokes the absorbed babysit function (rename a
                        surface, log layout target, etc.)

Per spec §0.2 (absorption pattern), the underlying babysit functions
are imported verbatim — the rule module is the new caller, the function
bodies are unchanged.

Rule IDs declared in ``src/atdd/coach/conventions/observer.convention.yaml``.
"""

__all__: list[str] = []
