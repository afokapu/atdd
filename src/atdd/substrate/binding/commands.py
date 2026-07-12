"""CLI handlers for the substrate binder (WMBT: binding-cli).

Two public commands over the locked substrate:

- ``atdd bind --check`` — compose the binding plan from the lock and write/validate
  ``.atdd/binding.lock.yaml``. A dry compose: it inspects manifests and does
  contract math only; it never provider-spawns an implementation.
- ``atdd capabilities`` — render which conventions are bound-owned vs left to a
  legacy-fallback validator, from the binding plan.
"""
from __future__ import annotations

import logging
from pathlib import Path

from atdd.substrate.binding import BindingError, plan as plan_mod

_log = logging.getLogger("atdd.substrate.binding")


def run_bind_check(*, project_root: str | Path = ".", write: bool = True) -> int:
    """Compose (and optionally write) the binding plan without executing any impl."""
    try:
        plan = plan_mod.build_binding_plan(project_root, log=lambda m: print(m))
    except BindingError as exc:
        _log.warning("bind --check refused", extra={"error": str(exc)})
        print(f"error: bind refused — {exc}")
        return 1

    bound = [c for c in plan["conventions"] if c["disposition"] == "bound"]
    fallback = [c for c in plan["conventions"] if c["disposition"] == "legacy-fallback"]
    if write:
        dest = plan_mod.write_binding_plan(project_root, plan)
        print(f"wrote {dest}  (keyed to {plan['substrate_lock_digest']})")
    print(f"binding plan: {len(bound)} bound, {len(fallback)} legacy-fallback")
    for c in bound:
        print(f"  bound           {c['convention_id']}  <- {c['implementation_id']} @ {c['workspace_id']}")
    for c in fallback:
        print(f"  legacy-fallback {c['convention_id']}")
    return 0


def run_capabilities(*, project_root: str | Path = ".") -> int:
    """Render bound-owned vs legacy-fallback conventions from the binding plan."""
    p = Path(project_root) / ".atdd" / plan_mod.PLAN_FILE
    if p.exists():
        import yaml

        from atdd.substrate.binding import schemas

        plan = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
        schemas.validate_binding_lock(plan, source=p)
    else:
        try:
            plan = plan_mod.build_binding_plan(project_root)
        except BindingError as exc:
            _log.warning("capabilities compose failed", extra={"error": str(exc)})
            print(f"error: {exc}")
            return 1

    conventions = plan.get("conventions", [])
    if not conventions:
        print("no bound capabilities (substrate has no gating implementations)")
        return 0
    for c in conventions:
        if c["disposition"] == "bound":
            print(f"bound           {c['convention_id']}  <- {c['implementation_id']} @ {c['workspace_id']}")
        else:
            print(f"legacy-fallback {c['convention_id']}")
    return 0
