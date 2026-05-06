# URN: component:govern-lifecycle:enforcement-substrate:spawn_harness_blocks:backend:application
# Runtime: python
# Purpose: Render the substrate's wmbt_rules / train_rules / security_rules YAML blocks for coach spawn-harness prompts (spec v12 §8.2).

"""Spawn-harness block renderers for repo-derived rules (issue #422).

Substrate spec v12 §8.2 — the coach's spawn-harness prompts include
parallel ``wmbt_rules:``, ``train_rules:``, and ``security_rules:``
blocks listing the repo rules in scope for the current coach phase. This
module renders the **security_rules** block; ``wmbt_rules`` /
``train_rules`` rendering lives in #417 (the broader spawn-harness
landing surface).

The module is intentionally pure — given a registry slice, it returns a
serializable dict structured exactly as spec §8.2 lines 625-633 show.
The caller (coach spawn machinery, when #417 lands) is responsible for
phase filtering and YAML serialization.

Field-name mapping (spec v12 §8.2 lines 625-633):

    ============================  ====================================
    YAML output field             RuleMetadata source
    ============================  ====================================
    feature_urn (block-level)     RuleMetadata.feature_urn
    id                            RuleMetadata.rule_id
    security_urn                  RuleMetadata.security_urn
    threat                        RuleMetadata.description (the
                                  ``<name> — <threat>`` composition)
    mitigation                    RuleMetadata.fix_hint
    severity                      RuleMetadata.severity
    acceptance_ref                RuleMetadata.bound_acceptance_urn
    ============================  ====================================

The ``acceptance_ref`` mapping is intentional: §8.2 uses the SHORT name
matching the source feature.yaml authoring surface; ``bound_acceptance_urn``
is the toolkit-internal name. Renderers expose the human-readable form.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional

from atdd.coach.utils.rule_binding import RuleMetadata


def render_security_rules_block(
    rules: Iterable[RuleMetadata],
    *,
    coach_phase: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Render the ``security_rules:`` block as a list of feature groups.

    Spec v12 §8.2 example:

      .. code-block:: yaml

        security_rules:
          - feature_urn: feature:auth:session-management
            rules:
              - id: repo.auth.session-management-security-001
                security_urn: security:auth:session-management:001
                threat: "Session Hijacking — Attacker steals session token via XSS"
                mitigation: "HttpOnly cookies, CSP headers"
                severity: 4
                acceptance_ref: acc:auth:D001-SEC-001-session-protection

    Args:
        rules: Iterable of ``RuleMetadata`` records (typically the
            registry's security-rule slice — i.e. those with
            ``bound_acceptance_urn`` populated).
        coach_phase: When supplied, filters to security rules whose
            ``phase`` matches the coach's current phase. Per spec §8.1
            paragraph 6 the security rule's activation phase equals the
            bound acceptance's phase, propagated to ``RuleMetadata.phase``
            by the walker (issue #422). When ``None``, no phase filter
            is applied.

    Returns:
        List of dicts, each with ``feature_urn`` and ``rules`` keys.
        Sorted deterministically by ``feature_urn`` then ``rule_id`` so
        snapshot tests are stable.
    """
    selected: List[RuleMetadata] = []
    for meta in rules:
        if not isinstance(meta, RuleMetadata):
            continue
        if not meta.bound_acceptance_urn:
            continue
        if not meta.security_urn or not meta.feature_urn:
            continue
        if coach_phase is not None and meta.phase and meta.phase != coach_phase:
            continue
        selected.append(meta)

    grouped: Dict[str, List[RuleMetadata]] = {}
    for meta in selected:
        grouped.setdefault(meta.feature_urn or "", []).append(meta)

    out: List[Dict[str, Any]] = []
    for feature_urn in sorted(grouped.keys()):
        entries = sorted(grouped[feature_urn], key=lambda m: m.rule_id)
        rule_blocks: List[Dict[str, Any]] = []
        for meta in entries:
            block: Dict[str, Any] = {
                "id": meta.rule_id,
                "security_urn": meta.security_urn,
                "threat": meta.description or "",
                "mitigation": meta.fix_hint or "",
                "severity": meta.severity,
                "acceptance_ref": meta.bound_acceptance_urn,
            }
            rule_blocks.append(block)
        out.append({
            "feature_urn": feature_urn,
            "rules": rule_blocks,
        })
    return out


__all__ = ["render_security_rules_block"]
