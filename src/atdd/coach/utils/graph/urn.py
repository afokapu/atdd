#!/usr/bin/env python3
r"""
URN Construction Utility
========================
Centralized URN generation for all entity types in the ATDD system.
All agents should use this utility to ensure consistent URN formatting.

URN Patterns:
- wagon:      wagon:{kebab-case-name}
              Example: wagon:resolve-dilemmas
              Pattern: ^wagon:[a-z][a-z0-9-]*$

- feature:    feature:{wagon}:{feature}
              Example: feature:resolve-dilemmas:binary-choice
              Pattern: ^feature:[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$

- wmbt:       wmbt:{wagon}:{STEP_CODE}{NNN}
              Example: wmbt:resolve-dilemmas:E001
              Pattern: ^wmbt:[a-z][a-z0-9-]*:[DLPCEMYRK][0-9]{3}$
              Step Codes: D=define, L=locate, P=prepare, C=confirm, E=execute, M=monitor, Y=modify, R=resolve, K=conclude

- acceptance: acc:{wagon}:{wmbt_id}-{harness}-{NNN}[-{slug}]   (WMBT shape)
              acc:{train_id}:{acceptance-slug}                  (train shape, spec v12 §3.3)
              Examples:
                acc:authenticate-user:C004-E2E-019
                acc:maintain-ux:C004-E2E-019-user-connection
                acc:0001-self-compliance-validate:idempotent-on-retry
              Pattern: ^acc:[a-z0-9][a-z0-9-]*:(WMBT-form|train-slug)$

- component:  component:{wagon}:{feature}:{name}:{side}:{layer}
              Example: component:resolve-dilemmas:binary-choice:OptionValidator:backend:domain
              Pattern: ^component:[a-z][a-z0-9-]*:[a-z][a-z0-9-]*:[a-zA-Z0-9.]+:(frontend|backend|fe|be):(presentation|application|domain|integration|assembly)$
              Side: frontend | backend | fe | be
              Layer: presentation | application | domain | integration | assembly

              Special forms:
              - Feature composition: component:{wagon}:{feature}:composition:{side}:assembly
              - Wagon entrypoint:    component:{wagon}:wagon:{name}:{side}:assembly
              - Train infra:         component:trains:{feature}:{name}:{side}:assembly

- security:   security:{wagon}:{feature-slug}:{NNN}
              Example: security:auth:session-management:001
              Pattern: ^security:[a-z][a-z0-9-]*:[a-z][a-z0-9-]*:[0-9]{3}$
              Threat-seq: zero-padded to 3 digits (e.g. THREAT-1 -> 001, THREAT-42 -> 042)

Parent-it-belongs-to principle (spec v12 §3.2)
----------------------------------------------
Each URN takes the form ``<resource>:<parent-coordinates>:<local-id>``, where
``<parent-coordinates>`` may require multiple colon-separated tokens depending on
how the parent is uniquely identified. URN segment count reflects the parent's
identification cost — it is not a fixed scheme depth. New resource families
register one entry in ``URNGrammar.PATTERNS`` and inherit the same convention
without re-litigating per-type rules.

Per-resource segment-count table (verbatim from spec §3.2):

  | Resource                                  | Parent                  | Total tokens after the prefix |
  | ----------------------------------------- | ----------------------- | ----------------------------- |
  | wagon:<id>                                | none                    | 1                             |
  | train:<id>                                | none                    | 1                             |
  | feature:<wagon>:<slug>                    | wagon (1 token)         | 2                             |
  | wmbt:<wagon>:<wmbt-id>                    | wagon (1 token)         | 2                             |
  | acc:<wagon>:<wmbt-id>-<harness>-<seq>     | WMBT (collapses)        | 2                             |
  | security:<wagon>:<feature-slug>:<seq>     | feature (2 tokens)      | 3                             |

The machine-readable mirror of this table is ``URNGrammar.SEGMENT_COUNTS``;
``test_urn_segment_count_table`` parametrizes over both to keep them in lockstep.

Usage:
    from utils.graph import URNGrammar
    # or
    from utils.graph.urn import URNGrammar

    # Build a wagon URN (verb-object format)
    wagon_urn = URNGrammar.wagon("manage-users")

    # Build a feature URN (verb-object format)
    feature_urn = URNGrammar.feature("manage-users", "authenticate-user")

    # Build a WMBT URN
    wmbt_urn = URNGrammar.wmbt("manage-users", "E001")

    # Build an acceptance URN
    acc_urn = URNGrammar.acceptance("manage-users", "C004", "E2E", "019")
    acc_urn_with_slug = URNGrammar.acceptance("manage-users", "C004", "E2E", "019", "user-login")

    # Build a component URN
    comp_urn = URNGrammar.component("manage-users", "authenticate-user", "LoginForm", "frontend", "presentation")

    # Build a test URN
    test_urn = URNGrammar.test("manage-users", "tc-login-success", feature_id="authenticate-user")
"""

import re
import sys
from functools import lru_cache
from pathlib import Path
from typing import Optional, Literal

import yaml

# No logger needed - removed _bootstrap dependency

# ---------------------------------------------------------------------------
# Convention-native grammar source (issue #1421).
#
# The URN grammar is DATA in ``urn_grammar.yaml``; this engine *executes* it, the
# same way ``planner/naming.py::verb_lexicon`` executes ``feature.convention.yaml``.
# Cycle safety is the non-negotiable constraint: this module imports zero atdd
# modules, and reads its grammar with plain ``yaml.safe_load`` + ``pathlib`` +
# ``@lru_cache`` ONLY — never through ``bind_rule`` or the convention-graph
# loader (that import would cycle). This is the identical discipline that keeps
# ``verb_lexicon`` cycle-free.
# ---------------------------------------------------------------------------
_GRAMMAR_PATH = Path(__file__).resolve().parent / "urn_grammar.yaml"


@lru_cache(maxsize=1)
def _load_grammar_families() -> dict:
    """Return the ``families:`` block of the URN grammar convention.

    Read once (``@lru_cache``) with plain ``yaml`` — the single source of the
    URN grammar. ``URNGrammar.PATTERNS`` / ``SEGMENT_COUNTS`` are projections of
    this; there is intentionally no second representation to drift from.
    """
    data = yaml.safe_load(_GRAMMAR_PATH.read_text(encoding="utf-8")) or {}
    return data.get("families", {}) or {}


class URNGrammar:
    """Centralized URN builder for all entity types."""

    STEP_LEGEND = {
        "D": "define",
        "L": "locate",
        "P": "prepare",
        "C": "confirm",
        "E": "execute",
        "M": "monitor",
        "Y": "modify",
        "R": "resolve",
        "K": "conclude",
    }
    STEP_NAMES = STEP_LEGEND
    STEP_CODE_LEGEND = STEP_LEGEND
    STEP_NAME_TO_CODE = {name: code for code, name in STEP_LEGEND.items()}

    # Harness code mapping (authoritative)
    HARNESS_CODES = {
        'unit': 'UNIT',
        'http': 'HTTP',
        'event': 'EVENT',
        'ws': 'WS',
        'e2e': 'E2E',
        'a11y': 'A11Y',
        'visual': 'VIS',
        'metric': 'METRIC',
        'job': 'JOB',
        'db': 'DB',
        'sec': 'SEC',
        'load': 'LOAD',
        'script': 'SCRIPT',
        'widget': 'WIDGET',
        'golden': 'GOLDEN',
        'bloc': 'BLOC',
        'integration': 'INTEGRATION',
        'rls': 'RLS',
        'edge_function': 'EDGE',
        'realtime': 'REALTIME',
        'storage': 'STORAGE',
        'smoke': 'SMOKE'
    }

    _MANIFEST_STATE = {}

    # ------------------------------------------------------------------
    # Grammar tables — PROJECTIONS of the ``urn_grammar.yaml`` convention
    # (issue #1421). These class attributes are no longer the source: they are
    # computed once, at class-definition time, from ``_load_grammar_families()``.
    # Every enforcing consumer (``validate_urn`` / ``validate_grammar`` /
    # ``parse_urn`` / the builder methods, plus external callers that read
    # ``URNGrammar.PATTERNS`` / ``SEGMENT_COUNTS``) sees the same single source,
    # so a family is added by editing one convention row — never this file.
    #
    #   PATTERNS       {family: regex}                — every family
    #   SEGMENT_COUNTS {family: token-count}          — only families that
    #                  declare one (parent-it-belongs-to; count == 1 ⇒ root)
    #   _FAMILY_SPECS  {family: full convention spec}  — drives segment-based parse
    # ------------------------------------------------------------------
    _FAMILY_SPECS = _load_grammar_families()
    PATTERNS = {
        family: spec["pattern"]
        for family, spec in _FAMILY_SPECS.items()
    }
    SEGMENT_COUNTS = {
        family: spec["segment_count"]
        for family, spec in _FAMILY_SPECS.items()
        if spec.get("segment_count") is not None
    }

    @classmethod
    def validate_urn(cls, urn: str, entity_type: str) -> bool:
        """Validate that a URN matches the expected pattern."""
        pattern = cls.PATTERNS.get(entity_type)
        if not pattern:
            raise ValueError(f"Unknown entity type: {entity_type}")
        return bool(re.match(pattern, urn))

    @classmethod
    def _alternate_segment_counts(cls, family: str) -> list:
        """Extra admissible token counts for a family with a polymorphic parent.

        Empty for every family that declares none — the exact-match segment-count
        check is the norm; ``acc`` is the sole exception (spec §3.3 gives it a
        wagon-parented AND a train-parented shape).
        """
        spec = cls._FAMILY_SPECS.get(family) or {}
        return list(spec.get('alternate_segment_counts') or [])

    @classmethod
    def validate_grammar(cls, urn: str) -> bool:
        """Validate a URN against the parent-it-belongs-to grammar (spec §3.2).

        Auto-detects the resource family from the prefix before the first
        ``:``. Returns ``True`` if the URN matches the registered pattern for
        that family. Raises ``ValueError`` with a clear, actionable message
        when:

        - the prefix is not a registered resource type, or
        - the segment count does not match ``SEGMENT_COUNTS`` for that family.

        This is the public entry point for the substrate spec's parent-it-
        belongs-to principle: every ``security:`` URN is a 3-token URN; every
        ``feature:`` URN is a 2-token URN; etc. Adding a new family means
        registering one ``PATTERNS`` entry plus one ``SEGMENT_COUNTS`` entry,
        not editing this method.
        """
        if not isinstance(urn, str) or ':' not in urn:
            raise ValueError(f"Malformed URN (missing prefix): {urn!r}")

        prefix = urn.split(':', 1)[0]
        if prefix not in cls.PATTERNS:
            known = ', '.join(sorted(cls.PATTERNS))
            raise ValueError(
                f"unknown resource type: {prefix!r} in URN {urn!r}. "
                f"Known resource types: {known}"
            )

        # Segment-count check (parent-it-belongs-to). Only enforced for
        # families with a declared expected count; other families (test,
        # contract, telemetry, plan, endpoint, ...) keep their existing
        # regex-only validation.
        expected = cls.SEGMENT_COUNTS.get(prefix)
        if expected is not None:
            actual = len(urn.split(':')) - 1  # tokens AFTER the prefix
            # A family whose PARENT is polymorphic has a polymorphic token count
            # too (``acc``: wagon-parented = 2, train-parented = 4 — #1548). Such
            # a family declares the extra counts in ``alternate_segment_counts``;
            # every other family has none and keeps the exact-match check.
            admissible = [expected, *cls._alternate_segment_counts(prefix)]
            if actual not in admissible:
                expected_txt = " or ".join(str(c) for c in admissible)
                raise ValueError(
                    f"{prefix!r} URN has wrong segment count: expected "
                    f"{expected_txt} token{'s' if admissible != [1] else ''} after "
                    f"'{prefix}:' per parent-it-belongs-to principle "
                    f"(spec §3.2), got {actual} in {urn!r}"
                )

        return cls.validate_urn(urn, prefix)

    @classmethod
    def wagon(cls, wagon_id: str) -> str:
        """
        Build a wagon URN.

        Args:
            wagon_id: The wagon identifier (lowercase, alphanumeric with hyphens)

        Returns:
            URN in format: wagon:[wagon_id]

        Example:
            URNGrammar.wagon("manage-users") -> "wagon:manage-users"
        """
        # Normalize the wagon ID
        wagon_id = cls._normalize_id(wagon_id)

        # Validate format
        if not re.match(r'^[a-z][a-z0-9-]*$', wagon_id):
            raise ValueError(f"Invalid wagon ID format: {wagon_id}. Must start with lowercase letter, contain only lowercase alphanumeric and hyphens.")

        urn = f"wagon:{wagon_id}"

        if not cls.validate_urn(urn, 'wagon'):
            raise ValueError(f"Generated invalid wagon URN: {urn}")

        return urn

    @classmethod
    def feature(cls, wagon_id: str, feature_id: str) -> str:
        """
        Build a feature URN.

        Args:
            wagon_id: The parent wagon identifier
            feature_id: The feature identifier

        Returns:
            URN in format: feature:[wagon_id]:[feature_id]

        Example:
            URNGrammar.feature("manage-users", "authenticate-user") -> "feature:manage-users:authenticate-user"
        """
        # Normalize IDs
        wagon_id = cls._normalize_id(wagon_id)
        feature_id = cls._normalize_id(feature_id)

        # Validate format
        if not re.match(r'^[a-z][a-z0-9-]*$', wagon_id):
            raise ValueError(f"Invalid wagon ID for feature: {wagon_id}")
        if not re.match(r'^[a-z][a-z0-9-]*$', feature_id):
            raise ValueError(f"Invalid feature ID: {feature_id}")

        urn = f"feature:{wagon_id}:{feature_id}"

        if not cls.validate_urn(urn, 'feature'):
            raise ValueError(f"Generated invalid feature URN: {urn}")

        return urn

    @classmethod
    def subject(cls, name: str) -> str:
        """
        Build a subject URN (issue #1421).

        ``subject:<name>`` is a 1-token root family — the durable noun object of
        a train's change (e.g. ``subject:artifact-identity``). It exists so a
        typed 2-token ``train:<subject>:<slug>`` has a real parent and is not
        flagged orphan by the graph model.

        Example:
            URNGrammar.subject("artifact-identity") -> "subject:artifact-identity"
        """
        name = cls._normalize_id(name)
        if not re.match(r'^[a-z][a-z0-9-]*$', name):
            raise ValueError(f"Invalid subject name: {name}. Must be kebab-case.")

        urn = f"subject:{name}"
        if not cls.validate_urn(urn, 'subject'):
            raise ValueError(f"Generated invalid subject URN: {urn}")

        return urn

    @classmethod
    def train(cls, subject: str, slug: str) -> str:
        """
        Build a typed train URN (issue #1421).

        ``train:<subject>:<slug>`` replaces the legacy ``train:NNNN-slug`` form.
        ``category`` is a validated FIELD, never an identity digit, so a
        reclassification changes metadata — not the identity.

        Example:
            URNGrammar.train("artifact-identity", "migrate-with-alias")
            -> "train:artifact-identity:migrate-with-alias"
        """
        subject = cls._normalize_id(subject)
        slug = cls._normalize_id(slug)
        if not re.match(r'^[a-z][a-z0-9-]*$', subject):
            raise ValueError(f"Invalid train subject: {subject}. Must be kebab-case.")
        if not re.match(r'^[a-z][a-z0-9-]*$', slug):
            raise ValueError(f"Invalid train slug: {slug}. Must be kebab-case.")

        urn = f"train:{subject}:{slug}"
        if not cls.validate_urn(urn, 'train'):
            raise ValueError(f"Generated invalid train URN: {urn}")

        return urn

    @classmethod
    def security(cls, wagon_id: str, feature_slug: str, threat_seq) -> str:
        """
        Build a security URN (spec v12 §3.2, parent = feature).

        Args:
            wagon_id: The grandparent wagon identifier
            feature_slug: The parent feature slug (kebab-case)
            threat_seq: Threat sequence — accepts an int (1..999), a 1-3 digit
                string, or a ``THREAT-<n>`` style id (case-insensitive). The
                numeric tail is zero-padded to three digits. ``THREAT-1`` -> "001",
                ``THREAT-42`` -> "042", ``"7"`` -> "007".

        Returns:
            URN in format: security:{wagon}:{feature_slug}:{NNN}

        Examples:
            URNGrammar.security("auth", "session-management", "001")
            -> "security:auth:session-management:001"

            URNGrammar.security("auth", "session-management", "THREAT-1")
            -> "security:auth:session-management:001"
        """
        wagon_id = cls._normalize_id(wagon_id)
        feature_slug = cls._normalize_id(feature_slug)

        if not re.match(r'^[a-z][a-z0-9-]*$', wagon_id):
            raise ValueError(f"Invalid wagon ID for security: {wagon_id}")
        if not re.match(r'^[a-z][a-z0-9-]*$', feature_slug):
            raise ValueError(f"Invalid feature slug for security: {feature_slug}")

        seq_str = cls._normalize_threat_seq(threat_seq)

        urn = f"security:{wagon_id}:{feature_slug}:{seq_str}"

        if not cls.validate_urn(urn, 'security'):
            raise ValueError(f"Generated invalid security URN: {urn}")

        return urn

    @classmethod
    def _normalize_threat_seq(cls, threat_seq) -> str:
        """Normalize a threat-seq value to a zero-padded 3-digit string.

        Accepts int, digit-only string, or ``THREAT-<n>`` style id
        (case-insensitive). Rejects values whose numeric tail is <1 or >999.
        """
        if isinstance(threat_seq, bool):  # bool is a subclass of int; reject explicitly
            raise TypeError("threat_seq must be an int or string, got bool")

        if isinstance(threat_seq, int):
            value = threat_seq
        elif isinstance(threat_seq, str):
            cleaned = threat_seq.strip()
            if not cleaned:
                raise ValueError("threat_seq cannot be empty")

            match = re.fullmatch(r'(?i)threat[-_]?(\d+)', cleaned)
            if match:
                value = int(match.group(1))
            elif re.fullmatch(r'\d+', cleaned):
                value = int(cleaned)
            else:
                raise ValueError(
                    f"Invalid threat_seq: {threat_seq!r}. Must be int, digits, or THREAT-<n>."
                )
        else:
            raise TypeError(f"threat_seq must be int or string, got {type(threat_seq).__name__}")

        if value < 1 or value > 999:
            raise ValueError(
                f"threat_seq numeric tail must be between 1 and 999 (got {value})"
            )

        return f"{value:03d}"

    @classmethod
    def wmbt(cls, wagon_id: str, sequence: str) -> str:
        """
        Build a WMBT URN.

        Args:
            wagon_id: The parent wagon identifier
            sequence: Step-coded identifier (e.g., "E001")

        Returns:
            URN in format: wmbt:[wagon_id]:[sequence]

        Example:
            URNGrammar.wmbt("user-auth", "E001") -> "wmbt:user-auth:E001"
        """
        # Normalize wagon ID
        wagon_id = cls._normalize_id(wagon_id)

        step_coded_id = cls._normalize_wmbt_id(sequence)

        # Validate wagon ID format
        if not re.match(r'^[a-z][a-z0-9-]*$', wagon_id):
            raise ValueError(f"Invalid wagon ID for WMBT: {wagon_id}")

        urn = f"wmbt:{wagon_id}:{step_coded_id}"

        if not cls.validate_urn(urn, 'wmbt'):
            raise ValueError(f"Generated invalid WMBT URN: {urn}")

        return urn

    @classmethod
    def step_from_id(cls, wmbt_id: str) -> str:
        """Derive the canonical step name from a step-coded WMBT id."""
        if not isinstance(wmbt_id, str):
            raise TypeError("wmbt_id must be a string")

        match = re.fullmatch(r'^[DLPCEMYRK][0-9]{3}$', wmbt_id.strip())
        if not match:
            raise ValueError(f"Invalid WMBT id format: {wmbt_id}")

        return cls.STEP_LEGEND[wmbt_id[0]]

    @classmethod
    def next_wmbt_id(cls, manifest: dict, step: str) -> str:
        """Return the next step-coded id for a given manifest and step."""
        if manifest is None:
            manifest = {}

        step_code = cls._normalize_step(step)
        current_wagon = manifest.get('wagon')

        state = cls._MANIFEST_STATE.get(id(manifest))
        if state is None or state.get('wagon') != current_wagon:
            state = {'wagon': current_wagon, 'counters': {}}
            cls._MANIFEST_STATE[id(manifest)] = state

        counters = state['counters']
        current_counter = counters.get(step_code)
        if current_counter is None:
            current_counter = cls._highest_wmbt_index(manifest, current_wagon, step_code)

        if current_counter >= 999:
            raise ValueError(f"No remaining ids for step {step}")

        next_index = current_counter + 1
        counters[step_code] = next_index

        return f"{step_code}{next_index:03d}"

    @classmethod
    def _highest_wmbt_index(cls, manifest: dict, current_wagon, step_code: str) -> int:
        """The highest NNN already used for this step code in the manifest's wmbt block."""
        existing = cls._wmbt_block_for_wagon(manifest, current_wagon)

        pattern = re.compile(rf'^{step_code}(\d{{3}})$')
        max_index = 0
        for key in existing.keys():
            if not isinstance(key, str):
                continue
            match = pattern.match(key)
            if match:
                max_index = max(max_index, int(match.group(1)))

        return max_index

    @staticmethod
    def _wmbt_block_for_wagon(manifest: dict, current_wagon) -> dict:
        """The manifest's wmbt block, empty when it clearly belongs to another wagon.

        A manifest whose produce[] entries never mention this wagon (or its
        leading token) is carrying someone else's wmbt block, so its ids must
        not seed this wagon's counter.
        """
        existing = manifest.get('wmbt') or {}
        if not isinstance(existing, dict):
            return {}

        wagon_slug = current_wagon or ""
        wagon_token = wagon_slug.split('-')[0] if wagon_slug else ""
        produce_entries = manifest.get('produce') or []
        if produce_entries and wagon_token:
            if all(
                wagon_slug not in str(entry) and wagon_token not in str(entry)
                for entry in produce_entries
            ):
                return {}

        return existing

    @classmethod
    def _normalize_step(cls, step: str) -> str:
        if not isinstance(step, str):
            raise TypeError("step must be a string")

        cleaned = step.strip()
        if not cleaned:
            raise ValueError("step cannot be empty")

        upper = cleaned.upper()
        if upper in cls.STEP_LEGEND:
            return upper

        lower = cleaned.lower()
        code = cls.STEP_NAME_TO_CODE.get(lower)
        if code:
            return code

        raise ValueError(f"Unknown step: {step}")

    @classmethod
    def _normalize_wmbt_id(cls, wmbt_id) -> str:
        if isinstance(wmbt_id, str):
            candidate = wmbt_id.strip().upper()
            if re.fullmatch(r'^[DLPCEMYRK][0-9]{3}$', candidate):
                return candidate
            raise ValueError("WMBT id must match pattern [DLPCEMYRK][0-9]{3}")

        raise TypeError("WMBT id must be provided as a step-coded string")

    @classmethod
    def _normalize_acceptance_sequence(cls, sequence) -> str:
        """Accept numeric or step-coded sequence values for acceptance URNs."""
        if isinstance(sequence, int):
            if sequence <= 0 or sequence > 999:
                raise ValueError("WMBT sequence must be between 1 and 999")
            return f"{sequence:03d}"

        if isinstance(sequence, str):
            cleaned = sequence.strip()
            if not cleaned:
                raise ValueError("WMBT sequence cannot be empty")

            upper = cleaned.upper()
            if re.fullmatch(r'^[DLPCEMYRK][0-9]{3}$', upper):
                return upper

            if re.fullmatch(r'^\d{1,3}$', cleaned):
                value = int(cleaned)
                if value <= 0 or value > 999:
                    raise ValueError("WMBT sequence must be between 1 and 999")
                return f"{value:03d}"

            raise ValueError("WMBT sequence must be a step-coded id or 1-3 digit number")

        raise TypeError("WMBT sequence must be an int or string")

    @classmethod
    def acceptance(cls, wagon_id: str, wmbt_id: str, harness_code: str, seq, slug: Optional[str] = None) -> str:
        """
        Build an acceptance URN (refactored format).

        Args:
            wagon_id: The parent wagon identifier
            wmbt_id: The WMBT ID (step code + seq, e.g., "C004", "E001")
            harness_code: The harness code (UPPERCASE, e.g., "E2E", "UNIT", "HTTP")
            seq: The per-harness sequence number (int or string, 001-999)
            slug: Optional kebab-case descriptor for readability

        Returns:
            URN in format: acc:{wagon}:{wmbt_id}-{harness}-{NNN}[-{slug}]

        Examples:
            URNGrammar.acceptance("authenticate-user", "C004", "E2E", "019")
            -> "acc:authenticate-user:C004-E2E-019"

            URNGrammar.acceptance("maintain-ux", "C004", "E2E", "019", "user-connection")
            -> "acc:maintain-ux:C004-E2E-019-user-connection"
        """
        wagon_id = cls._normalize_id(wagon_id)
        wmbt_id = cls._normalize_wmbt_id(wmbt_id)
        harness_code = cls._validate_harness_code(harness_code)
        seq_str = cls._normalize_sequence(seq)

        urn = f"acc:{wagon_id}:{wmbt_id}-{harness_code}-{seq_str}"

        # Add optional slug
        if slug:
            urn += f"-{cls._normalize_id(slug)}"

        # Validate final URN
        if not cls.validate_urn(urn, 'acc'):
            raise ValueError(f"Generated invalid acceptance URN: {urn}")

        return urn

    @classmethod
    def _validate_harness_code(cls, harness_code: str) -> str:
        """Uppercase the harness code and check it against HARNESS_CODES."""
        harness_code = harness_code.upper()
        valid_harnesses = set(cls.HARNESS_CODES.values())
        if harness_code not in valid_harnesses:
            raise ValueError(
                f"Invalid harness code: {harness_code}. "
                f"Must be one of: {', '.join(sorted(valid_harnesses))}"
            )
        return harness_code

    @staticmethod
    def _normalize_sequence(seq) -> str:
        """A 1-999 sequence (int or string) as a zero-padded 3-digit string."""
        if isinstance(seq, int):
            seq_int = seq
        elif isinstance(seq, str):
            seq_clean = seq.strip()
            if not re.match(r'^\d{1,3}$', seq_clean):
                raise ValueError("Sequence must be 1-3 digit number")
            seq_int = int(seq_clean)
        else:
            raise TypeError("Sequence must be int or string")

        if seq_int <= 0 or seq_int > 999:
            raise ValueError("Sequence must be between 1 and 999")
        return f"{seq_int:03d}"

    # Valid layers for component URNs
    COMPONENT_LAYERS = [
        'presentation', 'application', 'domain', 'integration', 'assembly',
    ]

    @classmethod
    def component(cls,
                  wagon_id: str,
                  feature_id: str,
                  component_name: str,
                  side: Literal['frontend', 'backend'],
                  layer: Literal['presentation', 'application', 'domain', 'integration', 'assembly']) -> str:
        """
        Build a component URN.

        Supports standard 4-layer components, feature composition (assembly),
        wagon entrypoints (feature_id='wagon'), and train infra (wagon_id='trains').

        Args:
            wagon_id: The parent wagon identifier (use 'trains' for train infra)
            feature_id: The parent feature identifier (use 'wagon' for wagon entrypoints)
            component_name: The component name (PascalCase, camelCase, or dot-separated)
            side: Either 'frontend' or 'backend'
            layer: The architectural layer (including 'assembly')

        Returns:
            URN in format: component:{wagon_id}:{feature_id}:{component_name}:{side}:{layer}

        Examples:
            URNGrammar.component("user-mgmt", "auth", "LoginForm", "frontend", "presentation")
            -> "component:user-mgmt:auth:LoginForm:frontend:presentation"

            URNGrammar.component("navigate-domains", "browse-hierarchy", "composition", "backend", "assembly")
            -> "component:navigate-domains:browse-hierarchy:composition:backend:assembly"

            URNGrammar.component("trains", "runner", "TrainRunner", "backend", "assembly")
            -> "component:trains:runner:TrainRunner:backend:assembly"
        """
        # Normalize IDs (but preserve component name case)
        wagon_id = cls._normalize_id(wagon_id)
        feature_id = cls._normalize_id(feature_id)

        cls._validate_component_parts(wagon_id, feature_id, component_name, side, layer)

        urn = f"component:{wagon_id}:{feature_id}:{component_name}:{side}:{layer}"

        if not cls.validate_urn(urn, 'component'):
            raise ValueError(f"Generated invalid component URN: {urn}")

        return urn

    @classmethod
    def _validate_component_parts(
        cls,
        wagon_id: str,
        feature_id: str,
        component_name: str,
        side: str,
        layer: str,
    ) -> None:
        """Every coordinate of a component URN, checked against the grammar."""
        if not re.match(r'^[a-z][a-z0-9-]*$', wagon_id):
            raise ValueError(f"Invalid wagon ID for component: {wagon_id}")
        if not re.match(r'^[a-z][a-z0-9-]*$', feature_id):
            raise ValueError(f"Invalid feature ID for component: {feature_id}")
        if not re.match(r'^[a-zA-Z0-9.]+$', component_name):
            raise ValueError(f"Invalid component name: {component_name}. Must be alphanumeric (dots allowed).")
        if side not in ['frontend', 'backend']:
            raise ValueError(f"Invalid side: {side}. Must be 'frontend' or 'backend'.")
        if layer not in cls.COMPONENT_LAYERS:
            raise ValueError(f"Invalid layer: {layer}. Must be one of: {', '.join(cls.COMPONENT_LAYERS)}.")

        # Train infra components must use assembly layer (S6.4)
        if wagon_id == 'trains' and layer != 'assembly':
            raise ValueError(f"Train infrastructure components must use 'assembly' layer, got: {layer}")

    @classmethod
    def plan(
        cls,
        wagon_id: str,
        feature_id: Optional[str] = None,
        component_name: Optional[str] = None,
        side: Optional[Literal['frontend', 'backend', 'fe', 'be']] = None,
        layer: Optional[
            Literal['presentation', 'application', 'domain', 'integration', 'assembly']
        ] = None,
    ) -> str:
        """
        Build a plan URN.

        Args:
            wagon_id: The wagon identifier
            feature_id: Optional feature identifier
            component_name: Optional component name
            side: Optional component side (requires component_name)
            layer: Optional architectural layer (requires component_name and side)

        Returns:
            URN in format: plan:[wagon][.[feature][.[component].[side].[layer]]]

        Examples:
            URNGrammar.plan("user-mgmt")
            -> "plan:user-mgmt"

            URNGrammar.plan("user-mgmt", feature_id="auth")
            -> "plan:user-mgmt.auth"

            URNGrammar.plan(
                "user-mgmt", feature_id="auth",
                component_name="LoginForm", side="fe", layer="presentation",
            )
            -> "plan:user-mgmt.auth.LoginForm.fe.presentation"
        """
        # Normalize IDs
        wagon_id = cls._normalize_id(wagon_id)

        # Build URN progressively
        urn = f"plan:{wagon_id}"

        if feature_id:
            feature_id = cls._normalize_id(feature_id)
            urn += f".{feature_id}"

            if component_name:
                if not side or not layer:
                    raise ValueError("Component requires both side and layer")
                urn += f".{component_name}.{side}.{layer}"
        elif component_name:
            raise ValueError("Cannot specify component without feature")

        if not cls.validate_urn(urn, 'plan'):
            raise ValueError(f"Generated invalid plan URN: {urn}")

        return urn

    @classmethod
    def contract(cls,
                 theme: str,
                 *hierarchy: str,
                 variant: Optional[str] = None) -> str:
        """
        Build a contract URN with colon hierarchy.

        Args:
            theme: The theme/domain (e.g., "mechanic", "match", "commons")
            *hierarchy: Additional hierarchy segments (colon-separated)
            variant: Optional variant suffix (dot-separated)

        Returns:
            URN in format: contract:{theme}(:{segment})*(.{variant})?

        Examples:
            URNGrammar.contract("mechanic", "timebank", variant="remaining")
            -> "contract:mechanic:timebank.remaining"

            URNGrammar.contract("match", "dilemma", "current")
            -> "contract:match:dilemma:current"

            URNGrammar.contract("commons", "ux", "foundations", "color")
            -> "contract:commons:ux:foundations:color"
        """
        # Normalize all segments
        theme = cls._normalize_id(theme)
        segments = [cls._normalize_id(s) for s in hierarchy]

        # Build URN with colon hierarchy
        urn = f"contract:{theme}"
        for segment in segments:
            urn += f":{segment}"

        # Add optional dot variant
        if variant:
            variant = cls._normalize_id(variant)
            urn += f".{variant}"

        if not cls.validate_urn(urn, 'contract'):
            raise ValueError(f"Generated invalid contract URN: {urn}")

        return urn

    @classmethod
    def telemetry(cls,
                  theme: str,
                  *hierarchy: str,
                  variant: Optional[str] = None) -> str:
        """
        Build a telemetry URN with colon hierarchy.

        Args:
            theme: The theme/domain (e.g., "mechanic", "match", "juggle")
            *hierarchy: Additional hierarchy segments (colon-separated)
            variant: Optional variant suffix (dot-separated)

        Returns:
            URN in format: telemetry:{theme}(:{segment})*(.{variant})?

        Examples:
            URNGrammar.telemetry("mechanic", "decision", variant="choice")
            -> "telemetry:mechanic:decision.choice"

            URNGrammar.telemetry("juggle", "goal", variant="detected")
            -> "telemetry:juggle:goal.detected"

            URNGrammar.telemetry("mechanic", "episode", variant="timer")
            -> "telemetry:mechanic:episode.timer"
        """
        # Normalize all segments
        theme = cls._normalize_id(theme)
        segments = [cls._normalize_id(s) for s in hierarchy]

        # Build URN with colon hierarchy
        urn = f"telemetry:{theme}"
        for segment in segments:
            urn += f":{segment}"

        # Add optional dot variant
        if variant:
            variant = cls._normalize_id(variant)
            urn += f".{variant}"

        if not cls.validate_urn(urn, 'telemetry'):
            raise ValueError(f"Generated invalid telemetry URN: {urn}")

        return urn

    @classmethod
    def test(
        cls,
        wagon_id: str,
        test_case: str,
        feature_id: Optional[str] = None,
        component_name: Optional[str] = None,
        side: Optional[Literal['frontend', 'backend', 'fe', 'be']] = None,
        layer: Optional[
            Literal['presentation', 'application', 'domain', 'integration', 'assembly']
        ] = None,
    ) -> str:
        """
        Build a test URN.

        Args:
            wagon_id: The wagon identifier
            test_case: The test case identifier (e.g., "tc-login-success")
            feature_id: Optional feature identifier
            component_name: Optional component name
            side: Optional component side (requires component_name)
            layer: Optional architectural layer (requires component_name and side)

        Returns:
            URN in format: test:[wagon][.[feature][.[component].[side].[layer]]].[test_case]

        Examples:
            URNGrammar.test("user-mgmt", "tc-basic-flow")
            -> "test:user-mgmt.tc-basic-flow"

            URNGrammar.test("user-mgmt", "tc-login", feature_id="auth")
            -> "test:user-mgmt.auth.tc-login"

            URNGrammar.test(
                "user-mgmt", "tc-render", feature_id="auth",
                component_name="LoginForm", side="fe", layer="presentation",
            )
            -> "test:user-mgmt.auth.LoginForm.fe.presentation.tc-render"
        """
        # Normalize IDs
        wagon_id = cls._normalize_id(wagon_id)
        test_case = cls._normalize_id(test_case)

        # Build URN progressively
        urn = f"test:{wagon_id}"

        if feature_id:
            feature_id = cls._normalize_id(feature_id)
            urn += f".{feature_id}"

            if component_name:
                if not side or not layer:
                    raise ValueError("Component requires both side and layer")
                urn += f".{component_name}.{side}.{layer}"

        urn += f".{test_case}"

        if not cls.validate_urn(urn, 'test'):
            raise ValueError(f"Generated invalid test URN: {urn}")

        return urn

    @classmethod
    def test_acceptance(
        cls,
        wagon_id: str,
        feature_id: str,
        wmbt_id: str,
        harness: str,
        seq: str,
        slug: str,
    ) -> str:
        """
        Build a V3 acceptance test URN.

        Args:
            wagon_id: Parent wagon identifier
            feature_id: Parent feature identifier
            wmbt_id: WMBT step-coded ID (e.g., "M002")
            harness: Harness code (e.g., "UNIT", "HTTP", "E2E")
            seq: 3-digit sequence (e.g., "003")
            slug: Kebab-case description (required)

        Returns:
            URN in format: test:{wagon}:{feature}:{WMBT_ID}-{HARNESS}-{NNN}-{slug}

        Example:
            URNGrammar.test_acceptance(
                "authenticate-identity", "verify-session",
                "M002", "UNIT", "003", "trace-spans-created",
            )
            -> "test:authenticate-identity:verify-session:M002-UNIT-003-trace-spans-created"
        """
        wagon_id = cls._normalize_id(wagon_id)
        feature_id = cls._normalize_id(feature_id)
        wmbt_id = cls._normalize_wmbt_id(wmbt_id)
        harness = harness.upper()
        slug = cls._normalize_id(slug)

        valid_harnesses = set(cls.HARNESS_CODES.values())
        if harness not in valid_harnesses:
            raise ValueError(f"Invalid harness: {harness}. Must be one of: {', '.join(sorted(valid_harnesses))}")

        if isinstance(seq, int):
            seq = f"{seq:03d}"
        seq = seq.strip().zfill(3)
        if not re.match(r'^\d{3}$', seq):
            raise ValueError(f"Invalid sequence: {seq}. Must be 3 digits.")

        if not slug:
            raise ValueError("slug is required for test URNs")

        urn = f"test:{wagon_id}:{feature_id}:{wmbt_id}-{harness}-{seq}-{slug}"

        if not cls.validate_urn(urn, 'test'):
            raise ValueError(f"Generated invalid test acceptance URN: {urn}")

        return urn

    @classmethod
    def test_journey(cls,
                     train_id: str,
                     harness: str,
                     seq: str,
                     slug: str) -> str:
        """
        Build a V3 journey (E2E) test URN.

        Args:
            train_id: Train identifier (NNNN-kebab-case)
            harness: Harness code (typically "E2E" for journey tests)
            seq: 3-digit sequence (e.g., "001")
            slug: Kebab-case description (required)

        Returns:
            URN in format: test:train:{train_id}:{HARNESS}-{NNN}-{slug}

        Example:
            URNGrammar.test_journey("0025-onboarding", "E2E", "001", "full-login-flow")
            -> "test:train:0025-onboarding:E2E-001-full-login-flow"
        """
        harness = harness.upper()
        slug = cls._normalize_id(slug)

        if not re.match(r'^\d{4}-[a-z0-9][a-z0-9-]*$', train_id):
            raise ValueError(f"Invalid train ID: {train_id}. Must match NNNN-kebab-case.")

        valid_harnesses = set(cls.HARNESS_CODES.values())
        if harness not in valid_harnesses:
            raise ValueError(f"Invalid harness: {harness}. Must be one of: {', '.join(sorted(valid_harnesses))}")

        if isinstance(seq, int):
            seq = f"{seq:03d}"
        seq = seq.strip().zfill(3)
        if not re.match(r'^\d{3}$', seq):
            raise ValueError(f"Invalid sequence: {seq}. Must be 3 digits.")

        if not slug:
            raise ValueError("slug is required for test URNs")

        urn = f"test:train:{train_id}:{harness}-{seq}-{slug}"

        if not cls.validate_urn(urn, 'test'):
            raise ValueError(f"Generated invalid test journey URN: {urn}")

        return urn

    @classmethod
    def parse_urn(cls, urn: str) -> dict:
        """
        Parse a URN into its components.

        Parsing is DATA-DRIVEN (issue #1421): the family is detected from the
        prefix and its colon tokens are mapped positionally onto the family's
        ``segments`` names declared in ``urn_grammar.yaml``. Adding a colon-only
        family therefore needs no branch here — just the convention row (plus a
        resolver in resolver.py and, optionally, a builder method).

        Two families whose terminal token is a dash-facet / multi-format
        sub-grammar (``acc``: ``wmbt_id-harness-seq[-slug]``; ``test``: the V3
        journey / acceptance / legacy-dot polymorphism whose train facet is tied
        to the still-legacy test-identity migration, #1421 Layer 6) are flagged
        ``parse: custom`` in the convention and keep dedicated parsers below.

        Args:
            urn: The URN to parse

        Returns:
            Dictionary with URN components (always includes a ``type`` key).
        """
        if not isinstance(urn, str) or ':' not in urn:
            raise ValueError(f"Unknown URN type: {urn}")

        prefix = urn.split(':', 1)[0]
        spec = cls._FAMILY_SPECS.get(prefix)

        # Families with a dash-facet / multi-format terminal token keep a
        # dedicated parser (declared ``parse: custom`` in the convention).
        if spec is not None and spec.get('parse') == 'custom':
            if prefix == 'acc':
                return cls._parse_acc(urn)
            if prefix == 'test':
                return cls._parse_test(urn)

        return cls._parse_by_segments(urn, prefix, spec)

    @classmethod
    def _parse_by_segments(cls, urn: str, prefix: str, spec: Optional[dict]) -> dict:
        """Generic, segment-driven parse for every colon-only family."""
        segments = (spec or {}).get('segments')
        if not spec or not segments:
            raise ValueError(f"Unknown URN type: {urn}")

        tokens = urn[len(prefix) + 1:].split(':')

        expected = spec.get('segment_count')
        if expected is not None and len(tokens) != expected:
            raise ValueError(
                f"Invalid {prefix} URN segment count: expected {expected} "
                f"token{'s' if expected != 1 else ''} after '{prefix}:' "
                f"(parent-it-belongs-to, spec §3.2), got {len(tokens)} in {urn!r}"
            )

        result = {'type': spec.get('parse_type', prefix)}
        for i, name in enumerate(segments):
            result[name] = tokens[i] if i < len(tokens) else None
        return result

    @classmethod
    def _parse_acc(cls, urn: str) -> dict:
        """Custom parser for the two ``acc`` shapes (spec §3.3).

        Train-parented — ``acc:train:<subject>:<slug>:<acceptance-slug>`` (#1548)
        — is detected first: it is the only shape whose parent is itself a typed,
        multi-token identity, so it is reassembled as a whole ``train_id`` rather
        than split across positional fields.

        Wagon-parented — ``acc:<wagon>:<wmbt_id>-<harness>-<seq>[-<slug>]`` — is
        the original shape and parses exactly as before.
        """
        main_part = urn[len('acc:'):]

        if main_part.startswith('train:'):
            tokens = main_part.split(':')
            # train, <subject>, <slug>, <acceptance-slug>
            if len(tokens) == 4:
                return {
                    'type': 'acceptance',
                    'parent_kind': 'train',
                    'train_id': ':'.join(tokens[:3]),
                    'subject': tokens[1],
                    'slug': tokens[3],
                }

        parts = main_part.split(':')
        # Format: wagon_id:wmbt_id-harness-seq[-slug]
        result = {
            'type': 'acceptance',
            'parent_kind': 'wagon',
            'wagon_id': parts[0] if len(parts) > 0 else None,
        }

        # Parse facets: wmbt_id-harness-seq[-slug]
        if len(parts) > 1:
            facets = parts[1].split('-')
            if len(facets) >= 3:
                result['wmbt_id'] = facets[0]  # e.g., C004
                result['harness'] = facets[1]  # e.g., E2E
                result['sequence'] = facets[2]  # e.g., 019
                # Optional slug (remaining parts joined with hyphens)
                if len(facets) > 3:
                    result['slug'] = '-'.join(facets[3:])

        return result

    @classmethod
    def _parse_test(cls, urn: str) -> dict:
        """Custom parser for the polymorphic ``test:`` family (journey /
        acceptance / legacy-dot). Its train facet still carries the legacy
        ``NNNN-slug`` train id, migrated by the test-identity work (#1421
        Layer 6), so this stays format-specific for now."""
        main_part = urn[5:]  # strip 'test:'

        # V3 journey format: test:train:{train_id}:{HARNESS}-{NNN}-{slug}
        if main_part.startswith('train:'):
            return cls._parse_test_journey(main_part[6:])  # strip 'train:'

        # V3 acceptance format: test:{wagon}:{feature}:{WMBT_ID}-{HARNESS}-{NNN}-{slug}
        acceptance = cls._parse_test_acceptance(main_part)
        if acceptance:
            return acceptance

        return cls._parse_test_legacy(main_part)

    @staticmethod
    def _parse_test_journey(train_part: str) -> dict:
        """``test:train:{train_id}:{HARNESS}-{NNN}-{slug}``."""
        colon_idx = train_part.find(':')
        if colon_idx <= 0:
            return {'type': 'test', 'format': 'journey', 'train_id': train_part}

        # Parse the tail: {HARNESS}-{NNN}-{slug}
        segments = train_part[colon_idx + 1:].split('-', 2)
        return {
            'type': 'test',
            'format': 'journey',
            'train_id': train_part[:colon_idx],
            'harness': segments[0] if len(segments) > 0 else None,
            'sequence': segments[1] if len(segments) > 1 else None,
            'slug': segments[2] if len(segments) > 2 else None,
        }

    @staticmethod
    def _parse_test_acceptance(main_part: str) -> Optional[dict]:
        """``test:{wagon}:{feature}:{WMBT_ID}-{HARNESS}-{NNN}-{slug}``. None if not one."""
        colon_parts = main_part.split(':')
        if len(colon_parts) != 3:
            return None

        wagon_id, feature_id, tail = colon_parts
        # First 3 dash-segments = WMBT_ID, HARNESS, NNN; the rest is the slug
        segments = tail.split('-', 3)
        if len(segments) < 3 or not re.match(r'^[A-Z]\d{3}$', segments[0]):
            return None

        return {
            'type': 'test',
            'format': 'acceptance',
            'wagon_id': wagon_id,
            'feature_id': feature_id,
            'wmbt_id': segments[0],
            'harness': segments[1],
            'sequence': segments[2],
            'slug': segments[3] if len(segments) > 3 else None,
        }

    @staticmethod
    def _parse_test_legacy(main_part: str) -> dict:
        """Legacy dot format: ``test:wagon.feature.tc-name``."""
        parts = main_part.split('.')
        result = {
            'type': 'test',
            'format': 'legacy',
            'wagon_id': parts[0] if len(parts) > 0 else None,
            'test_case': parts[-1] if parts else None,
        }
        if len(parts) > 2:
            result['feature_id'] = parts[1]
        if len(parts) > 5:
            result['component_name'] = parts[2]
            result['side'] = parts[3]
            result['layer'] = parts[4]
        return result

    @staticmethod
    def _normalize_id(identifier: str) -> str:
        """Normalize an identifier to lowercase with hyphens."""
        # Convert to lowercase
        normalized = identifier.lower()
        # Replace underscores with hyphens
        normalized = normalized.replace('_', '-')
        # Remove any spaces
        normalized = normalized.replace(' ', '-')
        # Collapse multiple hyphens
        normalized = re.sub(r'-+', '-', normalized)
        # Remove leading/trailing hyphens
        normalized = normalized.strip('-')
        return normalized


def _build_arg_parser():
    """The URN generator's CLI surface."""
    import argparse

    parser = argparse.ArgumentParser(description='Generate URNs for ATDD entities')
    subparsers = parser.add_subparsers(dest='entity', help='Entity type')

    wagon_parser = subparsers.add_parser('wagon', help='Generate wagon URN')
    wagon_parser.add_argument('wagon_id', help='Wagon identifier')

    feature_parser = subparsers.add_parser('feature', help='Generate feature URN')
    feature_parser.add_argument('wagon_id', help='Parent wagon identifier')
    feature_parser.add_argument('feature_id', help='Feature identifier')

    wmbt_parser = subparsers.add_parser('wmbt', help='Generate WMBT URN')
    wmbt_parser.add_argument('wagon_id', help='Parent wagon identifier')
    wmbt_parser.add_argument('sequence', help='Three-digit sequence (e.g., 001)')

    acc_parser = subparsers.add_parser('acceptance', help='Generate acceptance URN')
    acc_parser.add_argument('wagon_id', help='Parent wagon identifier')
    acc_parser.add_argument('wmbt_sequence', help='WMBT sequence number')
    acc_parser.add_argument('acceptance_id', help='Acceptance ID (e.g., AC-EXEC-201)')

    comp_parser = subparsers.add_parser('component', help='Generate component URN')
    comp_parser.add_argument('wagon_id', help='Parent wagon identifier')
    comp_parser.add_argument('feature_id', help='Parent feature identifier')
    comp_parser.add_argument('component_name', help='Component name')
    comp_parser.add_argument('side', choices=['frontend', 'backend'], help='Component side')
    comp_parser.add_argument('layer', choices=['presentation', 'application', 'domain', 'integration'], help='Architectural layer')

    parse_parser = subparsers.add_parser('parse', help='Parse a URN')
    parse_parser.add_argument('urn', help='URN to parse')

    validate_parser = subparsers.add_parser('validate', help='Validate a URN')
    validate_parser.add_argument('urn', help='URN to validate')
    validate_parser.add_argument('entity_type', choices=['wagon', 'feature', 'wmbt', 'acceptance', 'component'], help='Expected entity type')

    return parser


def _run_urn_command(args) -> int:
    """Run one URN subcommand. Returns the process exit code."""
    import json

    if args.entity == 'wagon':
        print(URNGrammar.wagon(args.wagon_id))
    elif args.entity == 'feature':
        print(URNGrammar.feature(args.wagon_id, args.feature_id))
    elif args.entity == 'wmbt':
        print(URNGrammar.wmbt(args.wagon_id, args.sequence))
    elif args.entity == 'acceptance':
        print(URNGrammar.acceptance(args.wagon_id, args.wmbt_sequence, args.acceptance_id))
    elif args.entity == 'component':
        print(URNGrammar.component(
            args.wagon_id, args.feature_id, args.component_name, args.side, args.layer
        ))
    elif args.entity == 'parse':
        print(json.dumps(URNGrammar.parse_urn(args.urn), indent=2))
    elif args.entity == 'validate':
        return _print_validation(args.urn, args.entity_type)
    else:
        print(f"Unsupported entity: {args.entity}")
        return 1

    return 0


def _print_validation(urn: str, entity_type: str) -> int:
    """Report whether a URN is valid for its entity type."""
    if URNGrammar.validate_urn(urn, entity_type):
        print(f"✓ Valid {entity_type} URN")
        return 0

    print(f"✗ Invalid {entity_type} URN")
    return 1


def main() -> int:
    """CLI interface for URN generation."""
    parser = _build_arg_parser()
    args = parser.parse_args()

    if not args.entity:
        parser.print_help()
        return 1

    try:
        return _run_urn_command(args)
    except ValueError as exc:  # atdd:suppress(coder.logging.coach-silent-swallow) UNTIL=2026-12-06
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == '__main__':
    main()
