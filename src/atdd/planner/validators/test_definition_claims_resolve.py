# URN: test:author-atdd-substrate:definition-anchor:C016-RED-001-claims-resolve
# Acceptance: acc:author-atdd-substrate:C016-UNIT-002-no-unsupported-field-claim
# WMBT: wmbt:author-atdd-substrate:C016
# Phase: RED
# Layer: integration
# Runtime: python
# Purpose: Enforce planner.definition.claims-must-resolve — a definition anchor may
#          not assert a field, an acronym expansion, or a mechanism its governing
#          authority does not support. RED on the live corpus; GREEN once corrected.
"""planner.definition.claims-must-resolve validator (#2039).

Sibling to ``planner.definition.anchor-required``, which requires the anchor to
EXIST, be ``kind: family`` and be graph-connected. This rule is about what the
anchor SAYS. They are separate rules on purpose: an anchor can be present,
family-kinded and connected while describing a different artifact.

Three assertion classes, one per defect class actually found in #2039. Each was
chosen because the other two cannot see it:

``acronym canon``
    A wrong acronym names no field, so the field check is blind to it. Three
    expansions of "WMBT" ship today.

``field claims``
    Read over the ``statement`` **and** the ``terms`` block, because both carry
    them — the feature anchor asserts ``status``/``acceptance`` (0 of 190 real
    files) and the wmbt anchor's terms assert ``id`` where the field is ``urn``.

``mechanism claims``
    Names no field at all, so it survives a field-only check. The interlocking
    anchor named one of its artifact's two routing authorities and omitted the
    other.

Precedence is corpus > owning validator > schema > prose (#760): a field in no
real artifact is wrong however the schema reads, and ``plan_unit_schema.py`` puts
``feature`` and ``wmbt`` on the *advise* tier because their schemas reject most
real files.

Convention: src/atdd/planner/conventions/nodes/planner.definition.claims-must-resolve.convention.yaml
Rule:       planner.definition.claims-must-resolve
Run:        atdd validate planner
"""
from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Dict, List, Set, Tuple

import pytest
import yaml

from atdd.coach.utils.disposition_gate import assert_disposition_satisfied
from atdd.coach.utils.repo import find_repo_root
from atdd.coach.utils.rule_binding import bind_rule
from atdd.coach.validators._violation import Violation

pytestmark = [pytest.mark.planner, pytest.mark.platform]

_RULE = bind_rule("planner.definition.claims-must-resolve")
_VALIDATOR_ID = "definition_claims_must_resolve"

REPO = find_repo_root()
NODES = REPO / "src" / "atdd" / "planner" / "conventions" / "nodes"
SCHEMAS = REPO / "src" / "atdd" / "planner" / "schemas"
PLAN = REPO / "plan"

CORE_ARTIFACTS = ("theme", "train", "interlocking", "wagon", "feature", "wmbt", "artifact")

#: The one expansion tracked source may carry, and the artifact it belongs to.
ACRONYM_CANON = {"WMBT": "What Must Be True"}

#: Generated output is not source; the graph builder's inventions are its own concern.
#: `docs/*-findings/` is excluded because an evidence archive QUOTES the defect it
#: documents — a review that records "expanded as 'What-Might-Break Test'" must not
#: itself trip the canon it is evidence for.
UNTRACKED_DIRS = ("graphify-out", ".git", "build", "node_modules")
EVIDENCE_DIRS = re.compile(r"^docs/[^/]*findings/")

#: Where each artifact's field vocabulary is decided. A kind with no JSON Schema
#: resolves to the validator that owns it rather than being skipped.
AUTHORITY: Dict[str, Tuple[str, ...]] = {
    "theme": ("validator:_theme_taxonomy",),
    "train": ("schema:train",),
    "interlocking": ("schema:train-interlocking", "schema:_dispatch"),
    "wagon": ("schema:wagon",),
    "feature": ("schema:feature", "corpus:features"),
    "wmbt": ("schema:wmbt", "corpus:wmbts"),
    "artifact": ("validator:_theme_taxonomy",),
}

def _tracked_files() -> List[Path]:
    """Every tracked file, per git — so generated output cannot pollute the canon."""
    out = subprocess.run(
        ["git", "-C", str(REPO), "ls-files"], capture_output=True, text=True, timeout=120
    )
    return [
        REPO / line
        for line in out.stdout.splitlines()
        if line
        and not any(line.startswith(d) for d in UNTRACKED_DIRS)
        and not EVIDENCE_DIRS.match(line)
    ]


def _initials(phrase: str) -> str:
    """The word-initials of a phrase — "What-Might-Break Test" -> "WMBT"."""
    return "".join(w[0].upper() for w in re.split(r"[\s-]+", phrase) if w)


def scan_acronym_canon() -> List[Violation]:
    """Exactly one expansion of each artifact acronym across tracked source.

    A candidate only counts when its word-initials spell the acronym. Without that
    filter the pattern also matches ordinary em-dash prose ("WMBT — Feature Coverage
    statement…"), which is not an expansion at all — three such false positives on
    the live corpus were what forced this filter.
    """
    violations: List[Violation] = []
    for acronym, canon in ACRONYM_CANON.items():
        pattern = re.compile(
            rf"{acronym}[sS]?\s*[(\u2014-]\s*([A-Z][A-Za-z-]*(?:[\s-]+[A-Za-z-]+){{1,5}})"
        )
        canon_norm = canon.replace("-", " ").lower()
        found: Dict[str, List[str]] = {}
        for path in _tracked_files():
            if path.suffix not in (".py", ".yaml", ".yml", ".json", ".md"):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            for match in pattern.finditer(text):
                expansion = " ".join(match.group(1).split())
                if _initials(expansion) != acronym:
                    continue  # prose, not an expansion
                if expansion.replace("-", " ").lower() == canon_norm:
                    continue
                found.setdefault(expansion, []).append(str(path.relative_to(REPO)))
        for expansion, where in sorted(found.items()):
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"{where[0]}:1",
                    detail=(
                        f"{acronym} is expanded as {expansion!r} in {len(where)} file(s) "
                        f"({', '.join(sorted(set(where))[:3])}); the canon is {canon!r}"
                    ),
                )
            )
    return violations


def _schema_fields(name: str) -> Set[str]:
    path = SCHEMAS / f"{name}.schema.json" if not name.startswith("_") else PLAN / f"{name}.schema.json"
    if not path.exists():
        return set()
    data = json.loads(path.read_text(encoding="utf-8"))
    fields = set(data.get("properties", {}))
    for block in (data.get("definitions") or {}, data.get("$defs") or {}):
        for sub in block.values():
            fields |= set((sub or {}).get("properties", {}) or {})
    return fields


def _corpus_fields(which: str) -> Set[str]:
    globs = {"features": "*/features/*.yaml", "wmbts": "*/[DLPCEMYRK][0-9][0-9][0-9].yaml"}
    fields: Set[str] = set()
    for f in PLAN.glob(globs[which]):
        try:
            doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(doc, dict):
            fields |= set(doc)
    return fields


def _validator_fields(module: str) -> Set[str]:
    """Field/vocabulary names a validator module owns, read from its source."""
    # Package-relative: this validator lives in the directory it scans, so anchor on
    # __file__ rather than assuming a source checkout at <repo>/src/atdd
    # (coach.code-roots.no-hardcoded-toolkit-root).
    hits = list(Path(__file__).resolve().parent.rglob(f"{module}*.py"))
    fields: Set[str] = set()
    for path in hits:
        text = path.read_text(encoding="utf-8", errors="replace")
        fields |= set(re.findall(r"[\"']([a-z][a-z0-9_]{2,})[\"']\s*:", text))
        fields |= set(re.findall(r"\bget\([\"']([a-z][a-z0-9_]{2,})[\"']", text))
    return fields


def authority_fields(artifact: str) -> Set[str]:
    fields: Set[str] = set()
    for spec in AUTHORITY.get(artifact, ()):
        kind, _, name = spec.partition(":")
        if kind == "schema":
            fields |= _schema_fields(name)
        elif kind == "corpus":
            fields |= _corpus_fields(name)
        elif kind == "validator":
            fields |= _validator_fields(name)
    return fields


#: Words that are fields somewhere in the substrate but read as ordinary domain
#: prose inside a definition. Mining un-backticked nouns is what catches the legacy
#: claims ("declares a urn, a status, and a non-empty acceptance section"), and this
#: is the cost of doing so. Backticked identifiers are the preferred form and need
#: no exemption; keep this list short and reviewable.
_PROSE_NOUNS = frozenset({
    "artifact", "signal", "when", "source", "section", "statement", "capability",
    "slice", "behavior", "journey", "input", "contract", "train", "wagon", "feature",
    "theme", "step", "sequence", "acceptances",
})


def all_authority_fields() -> Set[str]:
    """Every field name the plan substrate declares anywhere.

    A word that is a field for no artifact at all is prose, not a claim — this is
    what separates "status" (a real field, wrong for `feature`) from "exactly" and
    "smallest", which the grammar-based extraction also picks up.
    """
    fields: Set[str] = set()
    for artifact in CORE_ARTIFACTS:
        fields |= authority_fields(artifact)
    for name in ("acceptance", "component", "substrate", "appendix"):
        fields |= _schema_fields(name)
    return fields


def _claimed_fields(node: dict) -> Set[str]:
    """Field names a node asserts — in the statement and in every term.

    Read over `terms` as well as `statement` because both carry field claims: the
    wmbt anchor's `well-shaped` term asserts "id" where the field is `urn`, and the
    feature anchor's carries the status/acceptance claim verbatim.
    """
    blobs = [str(node.get("statement") or "")]
    for term in node.get("terms") or []:
        blobs.append(str(term.get("text") or ""))
        for value in (term.get("values") or {}).values():
            blobs.append(str(value))

    claimed: Set[str] = set()
    for blob in blobs:
        claimed |= set(re.findall(r"`([a-z][a-z0-9_.]{2,})`", blob))
        # "declares a urn, a status, and a non-empty acceptance section" — the list
        # continues past the verb, so take the whole clause and mine every noun.
        for m in re.finditer(r"\b(?:declares?|carries|carrying)\b([^.;]{0,160})", blob):
            for word in re.findall(r"[a-z][a-z0-9_]{2,}", m.group(1)):
                claimed.add(word)
    return {c.split(".")[0] for c in claimed}


def scan_field_claims() -> List[Violation]:
    """No definition anchor names a field its authority does not declare."""
    violations: List[Violation] = []
    # The `.shape` siblings carry the same field claims and some are `status: active`
    # — planner.feature.shape is the SOURCE of the feature drift, and the definition
    # node's terms cite it by name. A check scoped to `.definition` alone corrects the
    # echo and leaves the original (#2039 review finding).
    for artifact, suffix in (
        (a, s) for a in CORE_ARTIFACTS for s in ("definition", "shape")
    ):
        rule_id = f"planner.{artifact}.{suffix}"
        path = NODES / f"{rule_id}.convention.yaml"
        if not path.exists():
            continue  # anchor-required owns absence; not every kind has a shape node
        rel = f"src/atdd/planner/conventions/nodes/{rule_id}.convention.yaml"
        node = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        supported = authority_fields(artifact)
        if not supported:
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"{rel}:1",
                    detail=(
                        f"{artifact!r} has no resolvable authority in AUTHORITY — a kind with "
                        "no JSON Schema must name the validator that owns it, not be skipped"
                    ),
                )
            )
            continue
        known = all_authority_fields()
        candidates = _claimed_fields(node) - supported
        # Keep only words that ARE a field somewhere — a word that names no field
        # anywhere is prose. Singular/plural are the same claim.
        drifted = {
            c for c in candidates - _PROSE_NOUNS
            if (c in known or f"{c}s" in known)
            and not (f"{c}s" in supported or c.rstrip("s") in supported)
        }
        for field in sorted(drifted):
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"{rel}:1",
                    detail=(
                        f"{rule_id} asserts field {field!r}, which no governing authority "
                        f"for {artifact!r} declares ({', '.join(AUTHORITY[artifact])})"
                    ),
                )
            )
    return violations


#: Mechanism claims carry no field name, so the field check is blind to them.
#: Each entry: the anchor, a phrase it must contain, and why.
MECHANISM_CLAIMS: Tuple[Tuple[str, str, str], ...] = (
    (
        "interlocking",
        "guard",
        "a route references a declared guard (guard_ref -> fragments[].guards[]) and "
        "resolves under route_resolution.strategy; naming only the dispatch registry's "
        "artifact keying describes one of the artifact's two routing authorities",
    ),
    (
        "interlocking",
        "dispatch",
        "plan/_dispatch.schema.json is the Declared Dispatch Registry and does map a "
        "produced artifact_urn to a resolving train_id; dropping it deletes a true claim",
    ),
    (
        "wmbt",
        "acceptance",
        "a WMBT is made measurable by the acceptances that prove it — the anchor must say "
        "it is not itself a test",
    ),
)


def scan_mechanism_claims() -> List[Violation]:
    """Each anchor names every authority that governs its artifact's mechanism."""
    violations: List[Violation] = []
    for artifact, needle, why in MECHANISM_CLAIMS:
        rule_id = f"planner.{artifact}.definition"
        path = NODES / f"{rule_id}.convention.yaml"
        if not path.exists():
            continue
        rel = f"src/atdd/planner/conventions/nodes/{rule_id}.convention.yaml"
        blob = path.read_text(encoding="utf-8").lower()
        if needle.lower() not in blob:
            violations.append(
                Violation(
                    rule_id=_RULE.rule_id,
                    severity=_RULE.severity,
                    location=f"{rel}:1",
                    detail=f"{rule_id} never mentions {needle!r}: {why}",
                )
            )
    return violations


def scan_all() -> List[Violation]:
    return scan_acronym_canon() + scan_field_claims() + scan_mechanism_claims()


def test_definition_claims_resolve_against_authority() -> None:
    """Live corpus: every anchor's claims resolve against a governing authority."""
    assert_disposition_satisfied(validator_id=_VALIDATOR_ID, violations=scan_all())
