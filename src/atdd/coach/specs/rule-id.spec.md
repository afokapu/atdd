# Rule-ID Grammar SPEC

`SPEC-COACH-RULEID-0001..0007`

This SPEC governs the stable identifiers that label every rule declared in an
ATDD convention YAML. Rule IDs are the substrate that links convention text,
validator output, suppression markers, and fix recipes — and, since #399, the
two-way binding contract between rules and the validators that enforce them.

The grammar is closed and audited — every rule_id is namespaced under
`<archetype>.<convention>.<rule>`, where `archetype` is one of a fixed set.

---

## SPEC-COACH-RULEID-0001 — Grammar (namespaced, post-#399)

```
RULE_ID    ::= <archetype> "." <convention_short_name> "." <rule_name>
archetype  ::= coder | coach | tester | planner
convention_short_name ::= <segment> ("-" <segment>)*
                         ; filename of the declaring *.convention.yaml
                         ; minus the .convention.yaml suffix
                         ; (e.g. dead-code, error-response, rule-id)
rule_name  ::= <segment> ("-" <segment>)*
                         ; lowercase, hyphenated, human-readable
segment    ::= [a-z][a-z0-9]*
```

Compiled regex (machine-readable mirror in `rule-id.convention.yaml::grammar.pattern`):

```
^[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*\.[a-z][a-z0-9]*(-[a-z0-9]+)*$
```

Examples that conform:

- `coder.dead-code.unreachable-definitions`
- `coach.rule-id.stale-suppression`
- `planner.criteria.shape`
- `tester.smoke.harness-subprocess-failed-crash`

Examples that DO NOT conform:

- `GREEN-URN-001` — flat (legacy) grammar; allowed ONLY as an `aliases:` entry
  on a canonical rule, never as the canonical `id:`. Recognised via the
  `legacy_grammar:` block.
- `coder.dead-code` — must have three dot-separated segments.
- `Coder.dead-code.x` — must be lowercase.

Pre-#399 flat IDs (`<DOMAIN>-<TOPIC>-<NNN>`) are preserved as
`aliases:` on canonical rules and remain resolvable via `bind_rule()` and the
suppression scanner. The `legacy_grammar:` block in
`rule-id.convention.yaml` enumerates the residual patterns
(`^[A-Z][A-Z0-9]*(-[A-Z0-9]+){2,4}$`, plus `DS-NN`, `ERR-NN`, `GP-NN`,
`COACH-PRGATE-NNNN`).

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
   - id: coder.green.component-urn-marker-is
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
  - id: coder.dead-code.unreachable-definitions   # required, matches SPEC-COACH-RULEID-0001
    severity: 3                                   # required, int 1..5
    description: "..."                            # required, one-line human-readable
    disposition: strict                           # required: strict | suppress-and-clean | advisory | documentation-only
    validator: "test_dead_code_python::test_no_unreachable_definitions"  # required when disposition ≠ documentation-only
    fix_hint: "Either wire into a composition root, or delete it."        # optional canonical remediation
    aliases: ["DEAD-CODE-REACHABILITY-001"]       # optional legacy IDs this canonical rule supersedes
    recipe: adapter                               # optional, name of *.recipe.yaml peer
    introduced_in: "1.61.0"                       # optional, version string
    superseded_by: coder.dead-code.reachability-v2  # optional, see SPEC-COACH-RULEID-0004
```

The `rules:` array hangs off any convention concept block (e.g.
`green_phase.urn_naming.rules`, or top-level), as long as it lives inside the
declaring `*.convention.yaml`.

Field contract changes in #399:

- `disposition:` gains a fourth value `documentation-only` for rules that
  declare a principle but have no enforcing validator.
- `validator:` is REQUIRED when `disposition ∈ {strict, suppress-and-clean,
  advisory}` and MUST be absent when `disposition == documentation-only`.
- `validator:` value is `<module_basename>::<function_name>`. The dotted-import
  path is INFERRED from the rule's archetype:
  `atdd.<archetype>.validators.<module_basename>`.
- `fix_hint:` carries the canonical remediation; `Violation.fix_hint_ref` may
  still override per-emission.
- `aliases:` lists legacy ids (typically pre-#399 flat-grammar). The registry
  walker registers each alias as an additional dict key pointing at the same
  `RuleMetadata`, so `bind_rule(<flat_or_namespaced_id>)` resolves both.

---

## SPEC-COACH-RULEID-0007 — Bidirectional binding contract (#399)

Every enforced rule MUST be bound by the validator that emits it. Concretely:

1. The rule entry declares `validator: <module>::<function>`.
2. The named `module` is the basename of a Python file at
   `src/atdd/<archetype>/validators/<module>.py` (the archetype is the rule's
   first dot-segment).
3. The named `function` is a top-level `def` in that module.
4. Either the function body OR the module top level contains a literal
   `bind_rule("<canonical_id>")` call (an alias of the canonical id is also
   accepted).

The reverse-coherence validator
(`src/atdd/coach/validators/test_rule_validator_binding.py`) walks the
registry and FAILs CI when:

- An enforced rule has no `validator:` field.
- The named module or function does not exist.
- The function body / module level never calls `bind_rule(<this rule id>)`.
- A `documentation-only` rule carries a `validator:` field anyway.

The forward direction (every `bind_rule()` callsite resolves to a registered
rule) is policed by the existing
`test_rule_id_registry_coherence.py` validator. Together the two close the
loop.

The resolver
(`src/atdd/coach/utils/rule_validator_resolver.py`) AST-parses the validator
file as TEXT — it does NOT import the module. A single broken validator
therefore cannot cascade into an opaque collapse of the entire reverse
coherence pass; failures are surfaced as structured `Violation` records.

Emergency opt-out: `atdd validate coach --allow-orphan-rules`. This sets
`ATDD_ALLOW_ORPHAN_RULES=1` so the reverse-coherence validator demotes
failure to a `UserWarning`. The flag is for unblocking specific incidents,
not for permanent disablement.
