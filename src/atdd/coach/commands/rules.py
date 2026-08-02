# URN: component:govern-lifecycle:enforcement-substrate:rules_cli:backend:application
# Runtime: python
# Purpose: CLI command handler for `atdd rules {show,where,grep}` and the repo-rule listing peers under `atdd repo`.

"""``atdd rules`` and ``atdd repo {rules,wmbt-rules,train-rules}`` handlers.

Substrate spec v12 §9.2 — surface the merged rule registry to humans.

Six ``atdd rules`` subcommands (spec §5.7):

* ``atdd rules show <rule-id>`` — print the bound ``RuleMetadata`` (toolkit
  or repo). Legacy aliases resolve to canonical and surface BOTH forms
  so callers learn the canonical name while still seeing what they typed.
  *(Issue #493.)*
* ``atdd rules where <rule-id>`` — print the validator
  ``<module>::<function>`` callsite(s) and the inferred archetype-relative
  module path, plus the rule's source path and (for repo rules) the
  ``acceptance_urn`` discriminator. *(Issue #493.)*
* ``atdd rules grep <pattern>`` — case-insensitive substring search over
  rule-id, description, and aliases. Each line shows
  ``<rule-id>  sev=<n>  <disposition>  — <description>``. *(Issue #493.)*
* ``atdd rules disposition <strict|suppress-and-clean|advisory|documentation-only>``
  — list every rule with the given disposition. Repo rules are uniformly
  ``strict`` per substrate v12 §2; non-strict dispositions return toolkit
  rules only. *(Issue #494.)*
* ``atdd rules archetype <coder|coach|tester|planner|repo>`` — list every
  rule under the given archetype, sorted by rule-id for stable diffing.
  *(Issue #494.)*
* ``atdd rules suppressions [--stale-only] [--rule <id>]`` — list every
  active suppression marker as ``file_path:line  rule-id  UNTIL=<date>``.
  Markers referencing ``repo.*`` rules surface as warnings (substrate-
  unsuppressible per substrate v12 §2). *(Issue #494.)*

Three ``atdd repo`` listing peers (Track-A landing surface; Issue #414
renamed the legacy CLI namespace to ``atdd repo`` wholesale):

* ``atdd repo rules`` — every repo rule, grouped by parent URN.
* ``atdd repo wmbt-rules <wmbt-urn>`` — rules derived from one WMBT.
* ``atdd repo train-rules <train-urn>`` — rules derived from one train.

Implementation iterates the merged registry exposed by
``atdd.coach.utils.rule_binding.iter_rules`` so toolkit conventions and
repo-derived acceptance rules appear through one path (#408 walker).
"""
from __future__ import annotations

import json
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
from atdd.coach.utils.rule_validator_resolver import (
    ValidatorResolutionError,
    infer_module_path,
    parse_validator_field,
)
from atdd.coach.utils.suppression_scanner import (
    SuppressionMarker,
    find_stale_suppressions,
    find_suppressions,
)


# Per spec §5.7 — the disposition vocabulary is governed by
# ``acceptance-violation.convention.yaml``. The CLI surface enumerates the
# four valid values so an invalid input is reported with the full set.
_VALID_DISPOSITIONS: tuple = (
    "strict",
    "suppress-and-clean",
    "advisory",
    "documentation-only",
)

# Per substrate v12 §2 the substrate-derived archetype is ``repo``; the
# four toolkit archetypes are listed alongside so an invalid input is
# reported with the full set.
_VALID_ARCHETYPES: tuple = ("coder", "coach", "tester", "planner", "repo")


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
        # given/when/then are tuples per spec v12 §4.1 ("full lists"); join
        # for the text view so a multi-line clause renders on one row.
        ("given", "; ".join(meta.given) if meta.given else None),
        ("when", "; ".join(meta.when) if meta.when else None),
        ("then", "; ".join(meta.then) if meta.then else None),
        ("author", meta.author),
        ("created", meta.created),
    ]
    populated = [(k, v) for (k, v) in substrate_fields if v is not None]
    if populated:
        print()
        print("Substrate context:")
        for key, value in populated:
            print(f"  {key:<18} {value}")


class _Callsite:
    """One resolved validator callsite for ``atdd rules where``.

    ``validator_field`` is the verbatim ``<module>::<function>`` string;
    ``module_path`` is its archetype-relative import path
    (``src/atdd/<archetype>/validators/<module>.py``) when the path can
    be inferred, else a free-text marker explaining why it could not
    (e.g., a ``repo.*`` rule whose dispatcher is the substrate runner
    rather than a toolkit validator file).
    """

    __slots__ = ("validator_field", "module_path")

    def __init__(self, validator_field: str, module_path: str) -> None:
        self.validator_field = validator_field
        self.module_path = module_path


def _archetype_of(rule_id: str) -> str:
    """Return the leading archetype segment of *rule_id* (``a.b.c → a``)."""
    return rule_id.split(".", 1)[0] if "." in rule_id else rule_id


def _infer_module_path_str(archetype: str, module_basename: str) -> str:
    """Return the archetype-relative import path for *module_basename*.

    Falls back to ``src/atdd/<archetype>/validators/<module>.py`` even
    when ``infer_module_path`` rejects the archetype (e.g., ``repo``) so
    the surface still tells the operator where to look — repo rules
    point at the substrate dispatcher rather than a toolkit validator,
    and this string makes that explicit.
    """
    try:
        path = infer_module_path(archetype, module_basename)
        # Render the path relative to the toolkit src tree when possible
        # so the output is portable across install layouts; fall back to
        # the absolute path otherwise.
        marker = "src/atdd/"
        s = str(path)
        idx = s.find(marker)
        return s[idx:] if idx != -1 else s
    except ValidatorResolutionError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
        # Discovery surface, not a validator — the resolution miss is the
        # expected branch for `repo.*` archetypes whose dispatcher lives
        # outside ``src/atdd/<archetype>/validators/``. We render a
        # human-readable marker instead of swallowing silently; logging
        # would noise every legitimate repo-rule lookup.
        return (
            f"src/atdd/{archetype}/validators/{module_basename}.py "
            f"(substrate dispatcher)"
        )


def _resolve_callsites(meta: RuleMetadata) -> List[_Callsite]:
    """Return the validator callsites declared for *meta*.

    The current registry stores one ``validator`` string per rule. The
    helper still returns a list so the surface is honest about the
    "one callsite per line" framing and so a future YAML schema that
    permits multiple validators slots in without churn.
    """
    if not meta.validator:
        return []
    archetype = _archetype_of(meta.rule_id)
    try:
        module_basename, _func = parse_validator_field(meta.validator)
    except ValueError:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-10-31
        # Malformed validator field — surface the raw string with a
        # ``<malformed>`` marker so the operator can grep for it. This
        # is a discovery CLI; raising would crash the entire `where`
        # invocation when one rule has a typo'd validator field, and
        # the rule-binding validators (`test_rule_validator_binding`)
        # already enforce the format at validation time.
        return [_Callsite(validator_field=meta.validator, module_path="<malformed>")]
    module_path = _infer_module_path_str(archetype, module_basename)
    return [_Callsite(validator_field=meta.validator, module_path=module_path)]


class RulesCommand:
    """Handler for ``atdd rules {show,where,grep}``.

    Stateless — the registry walker is cached at the rule_binding layer.
    """

    def show(self, rule_id: str, format: str = "text") -> int:
        """Print the bound ``RuleMetadata`` for *rule_id*.

        Resolves through ``bind_rule`` so canonical ids and legacy aliases
        both work. When invoked with a legacy alias the surface displays
        BOTH the legacy form (so the operator sees what they typed) and
        the canonical id (so they learn the canonical name) per spec
        §5.7 / issue #493 acc:L001-UNIT-001. Exits non-zero when the rule
        is unregistered or ambiguous (declared in two places — a
        registry-level fault, not a user fault, but surfaced here so the
        CLI is honest about it).
        """
        try:
            meta = bind_rule(rule_id)
        except RuleNotInRegistryError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except AmbiguousRuleError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        is_alias = rule_id != meta.rule_id
        if format == "json":
            payload = _meta_to_dict(meta)
            if is_alias:
                payload["input_id"] = rule_id
                payload["resolved_from_alias"] = True
            print(json.dumps(payload, indent=2))
        else:
            if is_alias:
                print(
                    f"Resolved legacy alias {rule_id!r} → "
                    f"canonical {meta.rule_id!r}"
                )
                print()
            _print_metadata_text(meta)
        return 0

    def where(self, rule_id: str, format: str = "text") -> int:
        """Print the validator ``<module>::<function>`` callsite(s) for *rule_id*.

        Issue #493 acc:L001-UNIT-002 / spec §5.7: surface the validator
        reference and the import path inferred from the archetype
        (``coder.* → src/atdd/coder/validators/<module>.py``). Repo
        substrate rules carry the dispatcher reference set by the walker
        (signal-mode acceptances point at the metric runner). The YAML
        source path and (for repo rules) the ``acceptance_urn``
        discriminator are also printed so callers can grep the file for
        the matching block.
        """
        try:
            meta = bind_rule(rule_id)
        except RuleNotInRegistryError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        except AmbiguousRuleError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-08-31
            print(f"Error: {exc}", file=sys.stderr)
            return 1

        bindings = _resolve_callsites(meta)
        if format == "json":
            output = {
                "rule_id": meta.rule_id,
                "validator": meta.validator,
                "callsites": [
                    {
                        "validator_field": cs.validator_field,
                        "module_path": cs.module_path,
                    }
                    for cs in bindings
                ],
                "source_path": str(meta.source_path),
                "acceptance_urn": meta.acceptance_urn,
            }
            print(json.dumps(output, indent=2))
        else:
            print(f"rule_id:        {meta.rule_id}")
            if bindings:
                # One callsite per line — the spec phrases the surface as
                # "list every callsite, one per line" so an iteration here
                # keeps the format honest even when there is exactly one.
                for cs in bindings:
                    print(f"validator:      {cs.validator_field}")
                    print(f"module_path:    {cs.module_path}")
            else:
                print("validator:      <unbound — substrate harness dispatcher>")
            print(f"source_path:    {meta.source_path}")
            if meta.acceptance_urn is not None:
                print(f"acceptance_urn: {meta.acceptance_urn}")
        return 0

    def grep(self, pattern: str, format: str = "text") -> int:
        """List rules whose id, description, or alias contains *pattern*.

        Issue #493 acc:L001-UNIT-003 / spec §5.7: case-insensitive
        substring search across rule-id, description, and aliases. Each
        line shows ``<rule-id>  sev=<n>  <disposition>  — <description>``
        so the surface is consistent across toolkit and ``repo.*``
        archetypes. An empty result exits non-zero (grep convention)
        without crashing on regex special characters in the pattern.
        """
        needle = pattern.lower()
        matches: List[RuleMetadata] = []
        for meta in iter_rules():
            haystacks = [meta.rule_id, meta.description or ""]
            haystacks.extend(meta.aliases)
            if any(needle in h.lower() for h in haystacks):
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
            disposition = meta.disposition or "-"
            description = meta.description or ""
            print(
                f"{meta.rule_id}  sev={meta.severity}  {disposition}  — {description}"
            )
        print()
        print(f"Total: {len(matches)} rule(s) matched.")
        return 0

    def disposition(self, value: str, format: str = "text") -> int:
        """List every rule whose disposition equals *value*.

        Issue #494 acc:L002-UNIT-001 / spec §5.7. The disposition
        vocabulary is governed by ``acceptance-violation.convention.yaml``;
        an invalid input exits non-zero and surfaces the full set of valid
        options on stderr. Repo rules are uniformly ``strict`` per
        substrate v12 §2 (walker-set), so ``disposition strict`` returns
        repo + toolkit strict rules and the three other dispositions
        return only toolkit rules.

        Each line carries rule-id, archetype, severity, and a one-line
        description so the listing is self-explanatory at a glance.
        """
        if value not in _VALID_DISPOSITIONS:
            options = ", ".join(_VALID_DISPOSITIONS)
            print(
                f"Error: unknown disposition {value!r}. Valid options: {options}",
                file=sys.stderr,
            )
            return 1

        matches: List[RuleMetadata] = [
            meta for meta in iter_rules() if meta.disposition == value
        ]

        if format == "json":
            print(json.dumps([_meta_to_dict(m) for m in matches], indent=2))
            return 0

        if not matches:
            print(f"No rules with disposition={value!r}.")
            return 0
        for meta in matches:
            print(_format_rule_line(meta))
        print()
        print(
            f"Total: {len(matches)} rule(s) with disposition={value!r}."
        )
        return 0

    def archetype(self, value: str, format: str = "text") -> int:
        """List every rule under archetype *value*, sorted by rule-id.

        Issue #494 acc:L002-UNIT-002 / spec §5.7. ``archetype repo`` lists
        every substrate-derived rule (WMBT-acceptance, train-acceptance,
        security-derived) per substrate v12. The four toolkit archetypes
        return their respective toolkit rules. An unknown archetype exits
        non-zero and surfaces the five valid options on stderr.

        Output sorted ascending by rule-id within an archetype so a
        regenerated listing diffs cleanly against the previous run.
        """
        if value not in _VALID_ARCHETYPES:
            options = ", ".join(_VALID_ARCHETYPES)
            print(
                f"Error: unknown archetype {value!r}. Valid options: {options}",
                file=sys.stderr,
            )
            return 1

        matches: List[RuleMetadata] = sorted(
            (m for m in iter_rules() if _archetype_of(m.rule_id) == value),
            key=lambda m: m.rule_id,
        )

        if format == "json":
            print(json.dumps([_meta_to_dict(m) for m in matches], indent=2))
            return 0

        if not matches:
            print(f"No rules under archetype={value!r}.")
            return 0
        for meta in matches:
            print(_format_rule_line(meta))
        print()
        print(
            f"Total: {len(matches)} rule(s) under archetype={value!r}."
        )
        return 0

    def suppressions(
        self,
        roots: Optional[List[Path]] = None,
        stale_only: bool = False,
        rule_id: Optional[str] = None,
        format: str = "text",
    ) -> int:
        """List active ``atdd:suppress(...)`` markers across the repo.

        Issue #494 acc:L002-UNIT-003 / spec §5.7. Delegates to
        ``find_suppressions`` and ``find_stale_suppressions`` per the
        existing scanner contract.

        Args:
            roots: Directories to scan. Defaults to the current working
                directory — the CLI dispatcher passes the repo root.
            stale_only: When True, restricts output to markers whose
                ``UNTIL=`` date has passed today.
            rule_id: When set, restricts output to markers for that rule.
            format: ``text`` (default) or ``json``.

        Returns: ``0`` on success including empty results — the scanner is a
        discovery surface, not a gate. Markers referencing ``repo.*`` rules
        are surfaced as warnings on stderr because substrate v12 §2 makes
        repo rules unsuppressible regardless of the marker's presence.
        """
        scan_roots: List[Path] = list(roots) if roots else [Path.cwd()]

        if stale_only:
            markers = find_stale_suppressions(scan_roots)
        else:
            markers = find_suppressions(scan_roots)

        if rule_id is not None:
            markers = [m for m in markers if m.rule_id == rule_id]

        # Stable order: file path then line. The scanner walks rglob which
        # is filesystem-order so we sort here.
        markers = sorted(markers, key=lambda m: (str(m.file_path), m.line))

        repo_markers = [m for m in markers if m.rule_id.startswith("repo.")]

        if format == "json":
            payload = [
                {
                    "file_path": str(m.file_path),
                    "line": m.line,
                    "rule_id": m.rule_id,
                    "until": m.until.isoformat() if m.until else None,
                    "is_stale": m.is_stale,
                    "is_repo_rule": m.rule_id.startswith("repo."),
                }
                for m in markers
            ]
            print(json.dumps(payload, indent=2))
            # Repo-rule warnings still go to stderr in JSON mode so a
            # caller piping stdout to jq still sees the alert.
            for m in repo_markers:
                _warn_repo_rule_marker(m)
            return 0

        if not markers:
            print("No suppression markers found.")
            return 0
        for m in markers:
            print(_format_suppression_line(m))
        print()
        suffix = " (stale only)" if stale_only else ""
        print(f"Total: {len(markers)} marker(s){suffix}.")
        for m in repo_markers:
            _warn_repo_rule_marker(m)
        return 0


def _format_rule_line(meta: RuleMetadata) -> str:
    """Render one rule line for ``disposition`` / ``archetype`` listings.

    Format: ``<rule-id>  [<archetype>]  sev=<n>  <disposition>  — <description>``
    Carries the four context fields required by acc:L002-UNIT-001 (rule-id,
    archetype, severity, description) plus disposition for cross-reference
    use when ``archetype`` is the calling surface.
    """
    archetype = _archetype_of(meta.rule_id)
    disposition = meta.disposition or "-"
    description = meta.description or ""
    return (
        f"{meta.rule_id}  [{archetype}]  sev={meta.severity}  "
        f"{disposition}  — {description}"
    )


def _format_suppression_line(marker: SuppressionMarker) -> str:
    """Render one suppression marker line for the list output.

    Format: ``<file_path>:<line>  <rule-id>  UNTIL=<date>``. Markers
    without an ``UNTIL=`` segment render ``UNTIL=-`` so the column stays
    aligned even when a marker omits the date. A trailing ``[STALE]``
    or ``[REPO-RULE]`` tag flags the two non-default cases the operator
    most often cares about.
    """
    until = marker.until.isoformat() if marker.until else "-"
    tags: List[str] = []
    if marker.is_stale:
        tags.append("[STALE]")
    if marker.rule_id.startswith("repo."):
        tags.append("[REPO-RULE]")
    suffix = ("  " + " ".join(tags)) if tags else ""
    return (
        f"{marker.file_path}:{marker.line}  {marker.rule_id}  "
        f"UNTIL={until}{suffix}"
    )


def _warn_repo_rule_marker(marker: SuppressionMarker) -> None:
    """Emit a stderr warning for a marker referencing a ``repo.*`` rule.

    Substrate v12 §2 makes repo rules unsuppressible — the gate ignores
    the marker silently. Surfacing the warning here is the CLI's job:
    operators write the marker expecting absorption; without this line
    the misapplication is invisible until the next CI run.
    """
    print(
        f"Warning: {marker.file_path}:{marker.line} suppresses "
        f"{marker.rule_id!r}, but repo.* rules are unsuppressible "
        f"per substrate v12 §2. The marker is silently ignored by the "
        f"gate.",
        file=sys.stderr,
    )


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
    """Handler for the repo-rule listing peers under ``atdd repo``.

    Lives next to ``RulesCommand`` rather than inside ``URNCommand`` so
    the consumer (the CLI dispatcher) can hold one rule-aware command.
    Issue #414 renamed the legacy CLI namespace to ``atdd repo`` wholesale;
    this handler carries over unchanged.
    """

    def list_all_repo_rules(self, format: str = "text") -> int:
        """``atdd repo rules`` — every repo rule, grouped by parent URN."""
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
        """``atdd repo wmbt-rules <wmbt-urn>`` — rules derived from one WMBT."""
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

    def list_rules_for_feature(self, feature_urn: str, format: str = "text") -> int:
        """``atdd repo security-rules <feature-urn>`` — security rules for a feature.

        Iterates the merged registry and returns rules whose
        ``feature_urn`` matches *feature_urn*. Spec v12 §9.1 lists this
        subcommand as a peer of ``wmbt-rules`` / ``train-rules``; issue
        #422 wires it.
        """
        if not feature_urn.startswith("feature:"):
            print(
                f"Error: expected feature URN starting with 'feature:', got {feature_urn!r}",
                file=sys.stderr,
            )
            return 1

        matches = [
            m for m in _filter_repo_rules(iter_rules()) if m.feature_urn == feature_urn
        ]

        if format == "json":
            print(json.dumps([_meta_to_dict(m) for m in matches], indent=2))
            return 0 if matches else 1

        if not matches:
            print(f"No repo security rules derived from {feature_urn}.")
            return 1
        print(f"{feature_urn} ({len(matches)} security rule(s)):")
        for meta in sorted(matches, key=lambda m: m.rule_id):
            _print_repo_rule_line(meta)
            if meta.security_urn:
                print(f"      security_urn:        {meta.security_urn}")
            if meta.bound_acceptance_urn:
                print(f"      bound_acceptance_urn: {meta.bound_acceptance_urn}")
        return 0

    def list_rules_for_train(self, train_urn: str, format: str = "text") -> int:
        """``atdd repo train-rules <train-urn>`` — rules derived from one train."""
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
