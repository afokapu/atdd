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

- acceptance: acc:{wagon}:{wmbt_id}-{harness}-{NNN}[-{slug}]
              Example: acc:authenticate-user:C004-E2E-019
                       acc:maintain-ux:C004-E2E-019-user-connection
              Pattern: ^acc:[a-z][a-z0-9-]*:[DLPCEMYRK][0-9]{3}-(UNIT|HTTP|...)-[0-9]{3}(?:-[a-z0-9-]+)?$

- component:  component:{wagon}:{feature}:{objectCamelCase}:{side}:{layer}
              Example: component:resolve-dilemmas:binary-choice:OptionValidator:backend:domain
              Pattern: ^component:[a-z][a-z0-9-]*:[a-z][a-z0-9-]*:[a-zA-Z0-9]+:(frontend|backend):(presentation|application|domain|integration)$
              Side: frontend | backend
              Layer: presentation | application | domain | integration

Usage:
    from utils.graph import URNBuilder
    # or
    from utils.graph.urn import URNBuilder

    # Build a wagon URN (verb-object format)
    wagon_urn = URNBuilder.wagon("manage-users")

    # Build a feature URN (verb-object format)
    feature_urn = URNBuilder.feature("manage-users", "authenticate-user")

    # Build a WMBT URN
    wmbt_urn = URNBuilder.wmbt("manage-users", "E001")

    # Build an acceptance URN
    acc_urn = URNBuilder.acceptance("manage-users", "C004", "E2E", "019")
    acc_urn_with_slug = URNBuilder.acceptance("manage-users", "C004", "E2E", "019", "user-login")

    # Build a component URN
    comp_urn = URNBuilder.component("manage-users", "authenticate-user", "LoginForm", "frontend", "presentation")

    # Build a test URN
    test_urn = URNBuilder.test("manage-users", "tc-login-success", feature_id="authenticate-user")
"""

import re
import sys
from pathlib import Path
from typing import Optional, Literal

# No logger needed - removed _bootstrap dependency

class URNBuilder:
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
        'storage': 'STORAGE'
    }

    _MANIFEST_STATE = {}

    # Pattern validators
    PATTERNS = {
        # Identities
        'wagon': r'^wagon:[a-z][a-z0-9-]*$',
        'feature': r'^feature:[a-z][a-z0-9-]*:[a-z][a-z0-9-]*$',
        'component': r'^component:[a-z][a-z0-9-]*:[a-z][a-z0-9-]*:[a-zA-Z0-9]+:(frontend|backend|fe|be):(presentation|application|domain|integration|controller|usecase|repository)$',

        # Artifacts
        'plan': r'^plan:[a-z0-9]+(-[a-z0-9]+)*(\.[a-z0-9]+(-[a-z0-9]+)*)?(\.[a-zA-Z0-9]+\.(frontend|backend|fe|be)\.(presentation|application|domain|integration|controller|usecase|repository))?$',
        'test': r'^test:[a-z0-9]+(-[a-z0-9]+)*(\.[a-z0-9]+(-[a-z0-9]+)*)?(\.[a-zA-Z0-9]+\.(frontend|backend|fe|be)\.(presentation|application|domain|integration|controller|usecase|repository))?\.[a-z0-9-]+$',
        'contract': r'^contract:[a-z0-9]+(-[a-z0-9]+)*(\.[a-z0-9]+(-[a-z0-9]+)*)?(\.[a-zA-Z0-9]+\.(frontend|backend|fe|be)\.(presentation|application|domain|integration|controller|usecase|repository))?$',
        'telemetry': r'^telemetry:[a-z0-9]+(-[a-z0-9]+)*(\.[a-z0-9]+(-[a-z0-9]+)*)?(\.[a-zA-Z0-9]+\.(frontend|backend|fe|be)\.(presentation|application|domain|integration|controller|usecase|repository))?\.[a-z0-9-]+$',

        # ATDD Specific
        'wmbt': r'^wmbt:[a-z][a-z0-9-]*:[DLPCEMYRK][0-9]{3}$',
        'acc': r'^acc:[a-z][a-z0-9-]*:[DLPCEMYRK][0-9]{3}-(UNIT|HTTP|EVENT|WS|E2E|A11Y|VIS|METRIC|JOB|DB|SEC|LOAD|SCRIPT|WIDGET|GOLDEN|BLOC|INTEGRATION|RLS|EDGE|REALTIME|STORAGE)-[0-9]{3}(?:-[a-z0-9-]+)?$',

        # Resources
        'endpoint': r'^endpoint:[a-z0-9-]+\.(GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\.[a-z0-9-/]+$',
        'topic': r'^topic:[a-z0-9-]+$',
        'table': r'^table:[a-z0-9_]+$',
        'team': r'^team:[a-z0-9-]+$'
    }

    @classmethod
    def validate_urn(cls, urn: str, entity_type: str) -> bool:
        """Validate that a URN matches the expected pattern."""
        pattern = cls.PATTERNS.get(entity_type)
        if not pattern:
            raise ValueError(f"Unknown entity type: {entity_type}")
        return bool(re.match(pattern, urn))

    @classmethod
    def wagon(cls, wagon_id: str) -> str:
        """
        Build a wagon URN.

        Args:
            wagon_id: The wagon identifier (lowercase, alphanumeric with hyphens)

        Returns:
            URN in format: wagon:[wagon_id]

        Example:
            URNBuilder.wagon("manage-users") -> "wagon:manage-users"
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
            URNBuilder.feature("manage-users", "authenticate-user") -> "feature:manage-users:authenticate-user"
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
    def wmbt(cls, wagon_id: str, sequence: str) -> str:
        """
        Build a WMBT URN.

        Args:
            wagon_id: The parent wagon identifier
            sequence: Step-coded identifier (e.g., "E001")

        Returns:
            URN in format: wmbt:[wagon_id]:[sequence]

        Example:
            URNBuilder.wmbt("user-auth", "E001") -> "wmbt:user-auth:E001"
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
            existing = manifest.get('wmbt') or {}
            if not isinstance(existing, dict):
                existing = {}

            wagon_slug = current_wagon or ""
            wagon_token = wagon_slug.split('-')[0] if wagon_slug else ""
            produce_entries = manifest.get('produce') or []
            if produce_entries and wagon_token:
                if all(wagon_slug not in str(entry) and wagon_token not in str(entry) for entry in produce_entries):
                    existing = {}

            pattern = re.compile(rf'^{step_code}(\d{{3}})$')
            max_index = 0
            for key in existing.keys():
                if not isinstance(key, str):
                    continue
                match = pattern.match(key)
                if match:
                    max_index = max(max_index, int(match.group(1)))

            current_counter = max_index

        if current_counter >= 999:
            raise ValueError(f"No remaining ids for step {step}")

        next_index = current_counter + 1
        counters[step_code] = next_index

        return f"{step_code}{next_index:03d}"

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
            URNBuilder.acceptance("authenticate-user", "C004", "E2E", "019")
            -> "acc:authenticate-user:C004-E2E-019"

            URNBuilder.acceptance("maintain-ux", "C004", "E2E", "019", "user-connection")
            -> "acc:maintain-ux:C004-E2E-019-user-connection"
        """
        # Normalize wagon ID
        wagon_id = cls._normalize_id(wagon_id)

        # Validate and normalize WMBT ID
        wmbt_id = cls._normalize_wmbt_id(wmbt_id)

        # Validate harness code
        harness_code = harness_code.upper()
        valid_harnesses = set(cls.HARNESS_CODES.values())
        if harness_code not in valid_harnesses:
            raise ValueError(
                f"Invalid harness code: {harness_code}. "
                f"Must be one of: {', '.join(sorted(valid_harnesses))}"
            )

        # Normalize and pad sequence
        if isinstance(seq, int):
            if seq <= 0 or seq > 999:
                raise ValueError("Sequence must be between 1 and 999")
            seq_str = f"{seq:03d}"
        elif isinstance(seq, str):
            seq_clean = seq.strip()
            if not re.match(r'^\d{1,3}$', seq_clean):
                raise ValueError("Sequence must be 1-3 digit number")
            seq_int = int(seq_clean)
            if seq_int <= 0 or seq_int > 999:
                raise ValueError("Sequence must be between 1 and 999")
            seq_str = f"{seq_int:03d}"
        else:
            raise TypeError("Sequence must be int or string")

        # Build URN
        urn = f"acc:{wagon_id}:{wmbt_id}-{harness_code}-{seq_str}"

        # Add optional slug
        if slug:
            slug_normalized = cls._normalize_id(slug)
            urn += f"-{slug_normalized}"

        # Validate final URN
        if not cls.validate_urn(urn, 'acc'):
            raise ValueError(f"Generated invalid acceptance URN: {urn}")

        return urn

    @classmethod
    def component(cls,
                  wagon_id: str,
                  feature_id: str,
                  component_name: str,
                  side: Literal['frontend', 'backend'],
                  layer: Literal['presentation', 'application', 'domain', 'integration']) -> str:
        """
        Build a component URN.

        Args:
            wagon_id: The parent wagon identifier
            feature_id: The parent feature identifier
            component_name: The component name (PascalCase or camelCase)
            side: Either 'frontend' or 'backend'
            layer: The architectural layer

        Returns:
            URN in format: component:[wagon_id]:[feature_id]:[component_name]:[side]:[layer]

        Example:
            URNBuilder.component("user-mgmt", "auth", "LoginForm", "frontend", "presentation")
            -> "component:user-mgmt:auth:LoginForm:frontend:presentation"
        """
        # Normalize IDs (but preserve component name case)
        wagon_id = cls._normalize_id(wagon_id)
        feature_id = cls._normalize_id(feature_id)

        # Validate formats
        if not re.match(r'^[a-z][a-z0-9-]*$', wagon_id):
            raise ValueError(f"Invalid wagon ID for component: {wagon_id}")
        if not re.match(r'^[a-z][a-z0-9-]*$', feature_id):
            raise ValueError(f"Invalid feature ID for component: {feature_id}")
        if not re.match(r'^[a-zA-Z0-9]+$', component_name):
            raise ValueError(f"Invalid component name: {component_name}. Must be alphanumeric.")
        if side not in ['frontend', 'backend']:
            raise ValueError(f"Invalid side: {side}. Must be 'frontend' or 'backend'.")
        if layer not in ['presentation', 'application', 'domain', 'integration']:
            raise ValueError(f"Invalid layer: {layer}. Must be one of: presentation, application, domain, integration.")

        urn = f"component:{wagon_id}:{feature_id}:{component_name}:{side}:{layer}"

        if not cls.validate_urn(urn, 'component'):
            raise ValueError(f"Generated invalid component URN: {urn}")

        return urn

    @classmethod
    def plan(cls,
             wagon_id: str,
             feature_id: Optional[str] = None,
             component_name: Optional[str] = None,
             side: Optional[Literal['frontend', 'backend', 'fe', 'be']] = None,
             layer: Optional[Literal['presentation', 'application', 'domain', 'integration', 'controller', 'usecase', 'repository']] = None) -> str:
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
            URNBuilder.plan("user-mgmt")
            -> "plan:user-mgmt"

            URNBuilder.plan("user-mgmt", feature_id="auth")
            -> "plan:user-mgmt.auth"

            URNBuilder.plan("user-mgmt", feature_id="auth",
                          component_name="LoginForm", side="fe", layer="presentation")
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
                 wagon_id: str,
                 feature_id: Optional[str] = None,
                 component_name: Optional[str] = None,
                 side: Optional[Literal['frontend', 'backend', 'fe', 'be']] = None,
                 layer: Optional[Literal['presentation', 'application', 'domain', 'integration', 'controller', 'usecase', 'repository']] = None) -> str:
        """
        Build a contract URN.

        Args:
            wagon_id: The wagon identifier
            feature_id: Optional feature identifier
            component_name: Optional component name
            side: Optional component side (requires component_name)
            layer: Optional architectural layer (requires component_name and side)

        Returns:
            URN in format: contract:[wagon][.[feature][.[component].[side].[layer]]]

        Examples:
            URNBuilder.contract("user-mgmt")
            -> "contract:user-mgmt"

            URNBuilder.contract("user-mgmt", feature_id="auth")
            -> "contract:user-mgmt.auth"

            URNBuilder.contract("user-mgmt", feature_id="auth",
                              component_name="UserAPI", side="be", layer="controller")
            -> "contract:user-mgmt.auth.UserAPI.be.controller"
        """
        # Normalize IDs
        wagon_id = cls._normalize_id(wagon_id)

        # Build URN progressively
        urn = f"contract:{wagon_id}"

        if feature_id:
            feature_id = cls._normalize_id(feature_id)
            urn += f".{feature_id}"

            if component_name:
                if not side or not layer:
                    raise ValueError("Component requires both side and layer")
                urn += f".{component_name}.{side}.{layer}"
        elif component_name:
            raise ValueError("Cannot specify component without feature")

        if not cls.validate_urn(urn, 'contract'):
            raise ValueError(f"Generated invalid contract URN: {urn}")

        return urn

    @classmethod
    def telemetry(cls,
                  wagon_id: str,
                  signal: str,
                  feature_id: Optional[str] = None,
                  component_name: Optional[str] = None,
                  side: Optional[Literal['frontend', 'backend', 'fe', 'be']] = None,
                  layer: Optional[Literal['presentation', 'application', 'domain', 'integration', 'controller', 'usecase', 'repository']] = None) -> str:
        """
        Build a telemetry URN.

        Args:
            wagon_id: The wagon identifier
            signal: The signal identifier (e.g., "metric-response-time", "event-click")
            feature_id: Optional feature identifier
            component_name: Optional component name
            side: Optional component side (requires component_name)
            layer: Optional architectural layer (requires component_name and side)

        Returns:
            URN in format: telemetry:[wagon][.[feature][.[component].[side].[layer]]].[signal]

        Examples:
            URNBuilder.telemetry("user-mgmt", "metric-response-time")
            -> "telemetry:user-mgmt.metric-response-time"

            URNBuilder.telemetry("user-mgmt", "event-login", feature_id="auth")
            -> "telemetry:user-mgmt.auth.event-login"

            URNBuilder.telemetry("user-mgmt", "event-click", feature_id="auth",
                               component_name="LoginForm", side="fe", layer="presentation")
            -> "telemetry:user-mgmt.auth.LoginForm.fe.presentation.event-click"
        """
        # Normalize IDs
        wagon_id = cls._normalize_id(wagon_id)
        signal = cls._normalize_id(signal)

        # Build URN progressively
        urn = f"telemetry:{wagon_id}"

        if feature_id:
            feature_id = cls._normalize_id(feature_id)
            urn += f".{feature_id}"

            if component_name:
                if not side or not layer:
                    raise ValueError("Component requires both side and layer")
                urn += f".{component_name}.{side}.{layer}"
        elif component_name:
            raise ValueError("Cannot specify component without feature")

        urn += f".{signal}"

        if not cls.validate_urn(urn, 'telemetry'):
            raise ValueError(f"Generated invalid telemetry URN: {urn}")

        return urn

    @classmethod
    def test(cls,
             wagon_id: str,
             test_case: str,
             feature_id: Optional[str] = None,
             component_name: Optional[str] = None,
             side: Optional[Literal['frontend', 'backend', 'fe', 'be']] = None,
             layer: Optional[Literal['presentation', 'application', 'domain', 'integration', 'controller', 'usecase', 'repository']] = None) -> str:
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
            URNBuilder.test("user-mgmt", "tc-basic-flow")
            -> "test:user-mgmt.tc-basic-flow"

            URNBuilder.test("user-mgmt", "tc-login", feature_id="auth")
            -> "test:user-mgmt.auth.tc-login"

            URNBuilder.test("user-mgmt", "tc-render", feature_id="auth",
                          component_name="LoginForm", side="fe", layer="presentation")
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
    def parse_urn(cls, urn: str) -> dict:
        """
        Parse a URN into its components.

        Args:
            urn: The URN to parse

        Returns:
            Dictionary with URN components

        Example:
            URNBuilder.parse_urn("acc:user-auth.001.AC-EXEC-201")
            -> {
                'type': 'acceptance',
                'wagon_id': 'user-auth',
                'wmbt_sequence': '001',
                'acceptance_id': 'AC-EXEC-201'
            }
        """
        # Determine the type
        if urn.startswith('wagon:'):
            return {
                'type': 'wagon',
                'wagon_id': urn.replace('wagon:', '')
            }
        elif urn.startswith('feature:'):
            parts = urn.replace('feature:', '').split(':')
            return {
                'type': 'feature',
                'wagon_id': parts[0],
                'feature_id': parts[1] if len(parts) > 1 else None
            }
        elif urn.startswith('wmbt:'):
            parts = urn.replace('wmbt:', '').split(':')
            return {
                'type': 'wmbt',
                'wagon_id': parts[0],
                'sequence': parts[1] if len(parts) > 1 else None
            }
        elif urn.startswith('acc:'):
            main_part = urn.replace('acc:', '')
            parts = main_part.split(':')
            # Format: wagon_id:wmbt_id-harness-seq[-slug]
            result = {
                'type': 'acceptance',
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
        elif urn.startswith('test:'):
            main_part = urn.replace('test:', '')
            parts = main_part.split('.')
            # Last part is always the test case
            test_case = parts[-1] if parts else None
            # Rest follows wagon.feature.component.side.layer pattern
            result = {
                'type': 'test',
                'wagon_id': parts[0] if len(parts) > 0 else None,
                'test_case': test_case
            }
            if len(parts) > 2:
                result['feature_id'] = parts[1]
            if len(parts) > 5:  # Has component
                result['component_name'] = parts[2]
                result['side'] = parts[3]
                result['layer'] = parts[4]
            return result
        elif urn.startswith('component:'):
            parts = urn.replace('component:', '').split(':')
            return {
                'type': 'component',
                'wagon_id': parts[0] if len(parts) > 0 else None,
                'feature_id': parts[1] if len(parts) > 1 else None,
                'component_name': parts[2] if len(parts) > 2 else None,
                'side': parts[3] if len(parts) > 3 else None,
                'layer': parts[4] if len(parts) > 4 else None
            }
        else:
            raise ValueError(f"Unknown URN type: {urn}")

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


def main() -> int:
    """CLI interface for URN generation."""
    import argparse
    import json

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

    args = parser.parse_args()

    if not args.entity:
        parser.print_help()
        return 1

    exit_code = 0

    try:
        if args.entity == 'wagon':
            urn = URNBuilder.wagon(args.wagon_id)
            print(urn)
        elif args.entity == 'feature':
            urn = URNBuilder.feature(args.wagon_id, args.feature_id)
            print(urn)
        elif args.entity == 'wmbt':
            urn = URNBuilder.wmbt(args.wagon_id, args.sequence)
            print(urn)
        elif args.entity == 'acceptance':
            urn = URNBuilder.acceptance(args.wagon_id, args.wmbt_sequence, args.acceptance_id)
            print(urn)
        elif args.entity == 'component':
            urn = URNBuilder.component(args.wagon_id, args.feature_id, args.component_name, args.side, args.layer)
            print(urn)
        elif args.entity == 'parse':
            result = URNBuilder.parse_urn(args.urn)
            print(json.dumps(result, indent=2))
        elif args.entity == 'validate':
            is_valid = URNBuilder.validate_urn(args.urn, args.entity_type)
            if is_valid:
                print(f"✓ Valid {args.entity_type} URN")
            else:
                print(f"✗ Invalid {args.entity_type} URN")
                exit_code = 1
        else:
            print(f"Unsupported entity: {args.entity}")
            return 1
    except ValueError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    return exit_code


if __name__ == '__main__':
    main()
