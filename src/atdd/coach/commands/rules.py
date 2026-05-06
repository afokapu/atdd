# URN: component:govern-lifecycle:enforcement-substrate:rules_cli:backend:application
# Runtime: python
# Purpose: CLI command handler for `atdd rules {show,where,grep}` and the repo-rule listing peers under `atdd urn`.

"""``atdd rules`` and ``atdd urn {rules,wmbt-rules,train-rules}`` handlers.

Substrate spec v12 §9.2 — surface the merged rule registry to humans.

Three ``atdd rules`` subcommands:

* ``atdd rules show <rule-id>`` — print the bound ``RuleMetadata`` (toolkit
  or repo).
* ``atdd rules where <rule-id>`` — print the rule's source path (and YAML
  location for repo rules — the ``acceptance_urn`` it was derived from).
* ``atdd rules grep <pattern>`` — list every rule whose id or description
  matches the regex.

Three ``atdd urn`` listing peers (Track-A landing surface; Issue #414
renames ``atdd urn`` to ``atdd repo`` wholesale):

* ``atdd urn rules`` — every repo rule, grouped by parent URN.
* ``atdd urn wmbt-rules <wmbt-urn>`` — rules derived from one WMBT.
* ``atdd urn train-rules <train-urn>`` — rules derived from one train.

Implementation iterates the merged registry exposed by
``atdd.coach.utils.rule_binding.iter_rules`` so toolkit conventions and
repo-derived acceptance rules appear through one path (#408 walker).
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Iterable, List, Optional

from atdd.coach.utils.rule_binding import (
    AmbiguousRuleError,
    RuleMetadata,
    RuleNotInRegistryError,
    bind_rule,
    iter_rules,
)


def _meta_to_dict(meta: RuleMetadata) -> dict:
    """Render ``RuleMetadata`` as a JSON-serializable dict.

    ``source_path`` is a ``Path`` and ``aliases`` is a tuple — neither
    serializes via the default encoder, so cast both. ``fix_hint_ref``
    is a derived property, not a dataclass field, so add it explicitly.
    """
    out = asdict(meta)
    out["source_path"] = str(meta.source_path)
    out["aliases"] = list(meta.aliases)
    out["fix_hint_ref"] = meta.fix_hint_ref
    return out


def _print_metadata_text(meta: RuleMetadata) -> None:
    """Render a single ``RuleMetadata`` in human-readable form."""
    print(f"rule_id:           {meta.rule_id}")
    print(f"severity:          {meta.severity}")
    print(f"description:       {meta.description}")
    print(f"disposition:       {meta.disposition}")
    print(f"recipe:            {meta.recipe}")
    print(f"introduced_in:     {meta.introduced_in}")
    print(f"validator:         {meta.validator}")
    print(f"fix_hint_ref:      {meta.fix_hint_ref}")
    print(f"fix_hint:          {meta.fix_hint}")
    if meta.aliases:
        print(f"aliases:           {', '.join(meta.aliases)}")
    print(f"source_path:       {meta.source_path}")
    # Substrate-added discriminator / authoring context fields. Print only
    # the ones that are populated so toolkit rules (None on every field)
    # stay terse.
    substrate_fields = [
        ("acceptance_urn", meta.acceptance_urn),
        ("wmbt_urn", meta.wmbt_urn),
        ("train_urn", meta.train_urn),
        ("security_urn", meta.security_urn),
        ("feature_urn", meta.feature_urn),
        ("phase", meta.phase),
        ("harness_type", meta.harness_type),
        ("harness_category", meta.harness_category),
        ("signal_metric", meta.signal_metric),
        ("signal_threshold", meta.signal_threshold),
        ("given", meta.given),
        ("when", meta.when),
        ("then", meta.then),
        ("author", meta.author),
        ("created", meta.created),
    ]
    populated = [(k, v) for (k, v) in substrate_fields if v is not None]
    if populated:
        print()
        print("Substrate context:")
        for key, value in populated:
            print(f"  {key:<18} {value}")


class RulesCommand:
    """Handler for ``atdd rules {show,where,grep}``.

    Stateless — the registry walker is cached at the rule_binding layer.
    """

    def show(self, rule_id: str, format: str = "text") -> int:
        """Print the bound ``RuleMetadata`` for *rule_id*.

        Resolves through ``bind_rule`` so canonical ids and legacy aliases
        both work. Exits non-zero when the rule is unregistered or
        ambiguous (declared in two places — a registry-level fault, not a
        user fault, but surfaced here so the CLI is honest about it).
        """
        try:
            meta = bind_rule(rule_id)
        except RuleNotInRegistryError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except AmbiguousRuleError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        if format == "json":
            print(json.dumps(_meta_to_dict(meta), indent=2))
        else:
            _print_metadata_text(meta)
        return 0

    def where(self, rule_id: str, format: str = "text") -> int:
        """Print the rule's source path (and YAML location, if applicable).

        For toolkit rules the YAML location is the ``*.convention.yaml``
        path. For repo-derived rules (Track-A walker) the source path is
        the WMBT or train YAML, AND the ``acceptance_urn`` discriminator
        is printed so callers can grep the file for the matching block.
        """
        try:
            meta = bind_rule(rule_id)
        except RuleNotInRegistryError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except AmbiguousRuleError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        if format == "json":
            output = {
                "rule_id": meta.rule_id,
                "source_path": str(meta.source_path),
                "acceptance_urn": meta.acceptance_urn,
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"rule_id:        {meta.rule_id}")
            print(f"source_path:    {meta.source_path}")
            if meta.acceptance_urn is not None:
                print(f"acceptance_urn: {meta.acceptance_urn}")
        return 0

    def grep(self, pattern: str, format: str = "text") -> int:
        """List rules whose id or description matches *pattern* (regex)."""
        try:
            regex = re.compile(pattern)
        except re.error as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-07-03
            print(f"Error: invalid regex {pattern!r}: {exc}", file=sys.stderr)
            return 1

        matches: List[RuleMetadata] = []
        for meta in iter_rules():
            if regex.search(meta.rule_id) or regex.search(meta.description or ""):
                matches.append(meta)

        if format == "json":
            print(json.dumps(
                [_meta_to_dict(m) for m in matches], indent=2
            ))
            return 0 if matches else 1

        if not matches:
            print(f"No rules matched pattern {pattern!r}.")
            return 1
        for meta in matches:
            print(f"{meta.rule_id}")
            if meta.description:
                print(f"    {meta.description}")
        print()
        print(f"Total: {len(matches)} rule(s) matched.")
        return 0


def _filter_repo_rules(rules: Iterable[RuleMetadata]) -> List[RuleMetadata]:
    """Return only repo-derived rules from *rules* (archetype=='repo')."""
    return [m for m in rules if m.rule_id.startswith("repo.")]


def _print_repo_rule_line(meta: RuleMetadata, indent: int = 2) -> None:
    """Render ``rule_id`` (+ optional acceptance URN) for repo-rule listings."""
    pad = " " * indent
    print(f"{pad}{meta.rule_id}")
    if meta.acceptance_urn:
        print(f"{pad}  └─ {meta.acceptance_urn}")


class RepoRulesListing:
    """Handler for the repo-rule listing peers under ``atdd urn``.

    Lives next to ``RulesCommand`` rather than inside ``URNCommand`` so
    the consumer (the CLI dispatcher) can hold one rule-aware command.
    Issue #414 renames ``atdd urn`` to ``atdd repo`` wholesale; this
    handler carries over unchanged.
    """

    def list_all_repo_rules(self, format: str = "text") -> int:
        """``atdd urn rules`` — every repo rule, grouped by parent URN."""
        repo_rules = _filter_repo_rules(iter_rules())

        if format == "json":
            print(json.dumps(
                [_meta_to_dict(m) for m in repo_rules], indent=2
            ))
            return 0

        if not repo_rules:
            print("No repo rules derived from plan/.")
            return 0

        # Group by parent: WMBT URN if present, else train URN, else "<unknown>".
        groups: dict = {}
        for meta in repo_rules:
            parent = meta.wmbt_urn or meta.train_urn or "<unknown>"
            groups.setdefault(parent, []).append(meta)

        for parent in sorted(groups.keys()):
            metas = sorted(groups[parent], key=lambda m: m.rule_id)
            print(f"{parent} ({len(metas)} rule{'s' if len(metas) != 1 else ''}):")
            for meta in metas:
                _print_repo_rule_line(meta)
            print()
        print(f"Total: {len(repo_rules)} repo rule(s) across {len(groups)} parent(s).")
        return 0

    def list_rules_for_wmbt(self, wmbt_urn: str, format: str = "text") -> int:
        """``atdd urn wmbt-rules <wmbt-urn>`` — rules derived from one WMBT."""
        if not wmbt_urn.startswith("wmbt:"):
            print(
                f"Error: expected WMBT URN starting with 'wmbt:', got {wmbt_urn!r}",
                file=sys.stderr,
            )
            return 1

        matches = [
            m for m in _filter_repo_rules(iter_rules()) if m.wmbt_urn == wmbt_urn
        ]

        if format == "json":
            print(json.dumps([_meta_to_dict(m) for m in matches], indent=2))
            return 0 if matches else 1

        if not matches:
            print(f"No repo rules derived from {wmbt_urn}.")
            return 1
        print(f"{wmbt_urn} ({len(matches)} rule(s)):")
        for meta in sorted(matches, key=lambda m: m.rule_id):
            _print_repo_rule_line(meta)
        return 0

    def list_rules_for_train(self, train_urn: str, format: str = "text") -> int:
        """``atdd urn train-rules <train-urn>`` — rules derived from one train."""
        if not train_urn.startswith("train:"):
            print(
                f"Error: expected train URN starting with 'train:', got {train_urn!r}",
                file=sys.stderr,
            )
            return 1

        matches = [
            m for m in _filter_repo_rules(iter_rules()) if m.train_urn == train_urn
        ]

        if format == "json":
            print(json.dumps([_meta_to_dict(m) for m in matches], indent=2))
            return 0 if matches else 1

        if not matches:
            print(f"No repo rules derived from {train_urn}.")
            return 1
        print(f"{train_urn} ({len(matches)} rule(s)):")
        for meta in sorted(matches, key=lambda m: m.rule_id):
            _print_repo_rule_line(meta)
        return 0


__all__ = ["RulesCommand", "RepoRulesListing"]
