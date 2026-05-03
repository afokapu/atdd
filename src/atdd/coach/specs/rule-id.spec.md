# Rule-ID Grammar SPEC

`SPEC-COACH-RULEID-0001..0006`

This SPEC governs the stable identifiers that label every rule declared in an
ATDD convention YAML. Rule IDs are the substrate that links convention text,
validator output, ratchet baselines, suppression markers, and fix recipes.

The grammar is closed and audited — adding a new `DOMAIN` value is a SPEC edit,
not a free-form choice.

---

## SPEC-COACH-RULEID-0001 — Grammar

```
RULE_ID ::= <DOMAIN> "-" <TOPIC> "-" <NNN>
DOMAIN  ::= GREEN | RED | SMOKE | REFACTOR
          | COACH | PLANNER | TESTER
          | BOUNDARIES | DESIGN | SECURITY | LOGGING
          | DTO | ERROR | PRESENTATION
          | DUPLICATION | DEAD-CODE | COMPLEXITY
TOPIC   ::= [A-Z][A-Z0-9-]+        ; 1-3 hyphen-separated segments
                                   ; e.g. URN, URN-LAYER, FILE-HEADER-RUNTIME
NNN     ::= [0-9][0-9][0-9]        ; 3-digit zero-padded
```

Examples that conform:

- `GREEN-URN-001`
- `GREEN-URN-LAYER-002`
- `SECURITY-XSS-004`
- `COACH-RULEID-001`

Examples that DO NOT conform:

- `green-urn-001` (DOMAIN must be uppercase)
- `GREEN-URN-1` (NNN must be 3 digits, zero-padded)
- `MISC-FOO-001` (`MISC` is not in the closed DOMAIN set)
- `GREEN_URN_001` (separator must be `-`, not `_`)

---

## SPEC-COACH-RULEID-0002 — DOMAIN registry is closed

The DOMAIN values enumerated in 0001 are the entire allowed set. Adding a new
DOMAIN requires editing this SPEC and bumping its version. This prevents the
"two contributors invent different DOMAINs for the same area" drift that the
issue body (#340) calls out.

When a DOMAIN is added, the rule-id-uniqueness validator
(`src/atdd/coach/validators/test_rule_id_uniqueness.py`) reads the registry
from this SPEC's source of truth at
`src/atdd/coach/conventions/rule-id.convention.yaml::domains`. The SPEC is the
human-readable contract; the convention is the machine-readable source.

---

## SPEC-COACH-RULEID-0003 — Severity scale (1–5)

Every rule declares an integer `severity` in `[1, 5]`:

| Severity | Meaning              | Examples                                          |
|----------|----------------------|---------------------------------------------------|
| 1        | Advisory / style     | Comment style nits, ordering preferences          |
| 2        | Maintainability      | Naming, file-header completeness                  |
| 3        | Architectural        | URN markers, layer boundaries, composition rules  |
| 4        | Correctness risk     | Error handling, DTO validation, contract drift    |
| 5        | Security / blocking  | XSS, secret exposure, unsafe deserialization      |

Severity is an integer (not a named enum) so it sums cleanly into a per-PR
risk score: `risk = sum(v.severity for v in violations)`. Named enums would
force a brittle string-to-weight mapping later.

---

## SPEC-COACH-RULEID-0004 — Stability and lifecycle

A rule ID is published the first time its convention edit lands on `main`.
After that:

1. It is stable forever — the string never changes meaning.
2. To rename or replace a rule, declare both old and new for one release with
   `superseded_by:` on the old entry:

   ```yaml
   - id: GREEN-URN-001
     severity: 3
     superseded_by: GREEN-URN-LAYER-002
     description: "Component URN required as first non-empty line"
   - id: GREEN-URN-LAYER-002
     severity: 3
     description: "Component URN required, with layer segment, on first non-empty line"
   ```

3. Coach validation warns (not fails) when `superseded_by` is present, so
   downstream consumers see the migration window and can switch.
4. Removing the deprecated entry is a separate release.

SPEC names are themselves stable IDs (e.g. `SPEC-COACH-RULEID-0001..0006`),
so `superseded_by` migrations don't break inbound references.

---

## SPEC-COACH-RULEID-0005 — Recipe linkage

Rules MAY declare `recipe:` pointing at a `*.recipe.yaml` file in the same
directory tree. When a `Violation` is emitted, validators SHOULD populate
`fix_hint_ref` with `recipe:<name>#step-<n>` so self-fix tooling can route
the violation to the correct recipe step without re-deriving the link.

The recipe file format itself is governed by existing `*.recipe.yaml` files
(`adapter.recipe.yaml`, `complexity.recipe.yaml`, `design.recipe.yaml`); this
SPEC only governs the linkage from a rule.

---

## SPEC-COACH-RULEID-0006 — Per-rule YAML shape

A rule entry in a convention YAML has the shape:

```yaml
rules:
  - id: GREEN-URN-001               # required, matches SPEC-COACH-RULEID-0001
    severity: 3                     # required, int 1..5
    description: "..."              # required, one-line human-readable
    recipe: adapter                 # optional, name of *.recipe.yaml peer
    introduced_in: "1.61.0"         # optional, version string
    superseded_by: GREEN-URN-002    # optional, see SPEC-COACH-RULEID-0004
```

The `rules:` array hangs off any top-level convention concept block (e.g.
`green_phase.urn_naming.rules`, not at the file root). This keeps rule IDs
locally readable next to the rule text.
