# Registry-scope decision: `atdd validate` (Path A) stays core-only

**Decision (#1427 govern-registry / D001).** The `atdd validate` rule registry —
the set of rules Path A reads and enforces — stays rooted at the core `src/atdd`
convention tree **alone**, by design. The extension convention nodes under
`.atdd/extensions` are **not** admitted into that registry. This is recorded here
with its evidence rather than left to assumption.

## Why core-only

`atdd validate` builds its registry from
`atdd.coach.utils.rule_binding.find_convention_files()`, whose default search roots
are the core package (`src/atdd`). The evidence, measured with the same walker the
rule-id uniqueness validator uses (`extract_rules`):

| Measurement | Value |
| --- | --- |
| Files admitted into the core registry that live under `.atdd/extensions` | **0 of 324** |
| Core rule_ids | **373** |
| Extension rule_ids | **50** |
| Core ∩ extension rule_ids | **50** |
| Extension-only rule_ids (present in extensions, absent from core) | **0** |

Every extension convention node is a **high-fidelity mirror** of a live core rule:
each carries `source.legacy_path` + `source.legacy_rule_id` pointing back at the
core rule it reproduces, and its own `rule_id` equals that `legacy_rule_id`. So the
50 extension rule_ids are a strict subset of the 373 core rule_ids.

**Consequence:** wiring Path A to also read `.atdd/extensions` would add **zero new
rules** and introduce **50 duplicate rule_ids** — every admitted node would collide
with the core rule it mirrors. It cannot enforce anything the core registry does not
already enforce. The core-only scope is therefore not a limitation to be lifted; it
is the correct boundary.

## What guards the boundary

The decision is backed by executable guards in `atdd.enforce.registry`
(tests under `src/atdd/enforce/tests/`):

- **D001 registry-scope** — `core_rule_ids` / `extension_rule_ids` +
  `new_rules_from_extensions` / `duplicate_rule_ids` prove the merge adds no rule
  and only duplicates, and that the live core registry admits no extension file.
- **E001 mirror-coherence** — `find_mirror_incoherences` / `assert_mirrors_coherent`
  fail loudly if any extension node's `legacy_rule_id` stops resolving to a live
  core rule (the mirror drifted because its core twin was renamed or deleted).
- **E002 duplicate-precedence** — `assert_core_precedes_extension` raises
  `DuplicateRuleError` on any cross-registry collision, stating the precedence:
  **CORE precedes extension**, the core declaration is authoritative.
- **E003 core-succession** — because no CI job runs Path B (`atdd enforce`) as a
  *blocking* gate (the `enforce-extensions` job's convention verdict is advisory /
  `continue-on-error`), every extension rule is enforced **solely by its blocking
  core twin under Path A**. `guard_core_deletion` therefore refuses deleting a core
  node whose extension twin is not both bound and blockingly enforced — otherwise
  the deletion silently strips the only enforcement of that obligation.

## The latent hole this closes

The extension mirror set exists to make the persona-aware ID grammar (#1343/#1344) a
lock regeneration rather than a rule migration — not to add a second, independent
enforcement path. Until Path B is promoted to a blocking gate, deleting a core
convention node is the way enforcement silently disappears: Path A stops enforcing
the rule, and the advisory Path B run does not fail the build. E003 is the guard
that makes that failure loud.
