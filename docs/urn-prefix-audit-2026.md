# URN-Prefix Hardcoding Audit (2026)

> **Issue:** #421 — *substrate Track-G-urn-audit*
> **Spec:** `docs/specs/atdd-repo-substrate-spec-v12.md` §10.0 Workstream A (A.6)
> **Plan:** `docs/specs/atdd-repo-substrate-issues.md` (Issue #15)
> **Audit completed:** 2026-05-06
> **Branch / PR:** `feat/substrate-421-urn-audit` → main (PR linked from this commit)

## 1. Goal

Verify that introducing a new URN family in the toolkit requires changes only
to the documented extension points (one resolver class, one `URNBuilder.PATTERNS`
entry, one branch in `URNBuilder.parse_urn`, optionally a builder method) — and
to **no other call site**: validators, CLI subcommand registries, test discovery,
and graph builders must stay untouched.

The audit walks the toolkit's source tree, fixtures, recipe YAMLs, agent
prompts, and CI scripts looking for hardcoded URN-family lists that would
violate this contract. Every finding is classified per the issue body:

- **(a)** Should iterate `ResolverRegistry().families()` — list represents
  *URN-families-currently-registered*.
- **(b)** Should iterate `URNBuilder.PATTERNS.keys()` (or
  `URNBuilder.SEGMENT_COUNTS.items()`) — list represents *URN-syntax-recognized*.
- **(c)** Intentionally closed — keep the list, but anchor it with a
  centralized exempt comment that points back to this report.

The throwaway demonstration lives in
[`src/atdd/coach/utils/graph/tests/test_urn_extension_contract.py`](../src/atdd/coach/utils/graph/tests/test_urn_extension_contract.py)
and registers a `theatre:` URN family behind a `monkeypatch` fixture (the
"test-only flag"). The full graph test suite (108 tests) passes with no edits
elsewhere.

## 2. Code sites searched

The audit grepped the entire repository (excluding `.git`, `__pycache__`,
`node_modules`, `dist`, `build`, `.venv`) for the following signatures:

1. Set / list / tuple literals containing two or more known URN family
   strings (`wagon`, `feature`, `wmbt`, `acc`, `component`, `train`,
   `security`, `contract`, `telemetry`, `test`, `table`, `migration`,
   `endpoint`, `topic`, `team`, `plan`).
2. Equality and `in` checks on `family` / `prefix` variables against
   string literals.
3. Constants named `URN_PREFIXES`, `URN_FAMILIES`, `URN_TYPES`,
   `RESOLVER_TYPES`, `ALLOWED_URN_FAMILIES`, `VALID_URN_FAMILIES`,
   `KNOWN_FAMILIES`, `FAMILIES`, `PREFIXES`.
4. `subparsers.add_parser` / `add_argument(... choices=...)` with URN
   family names.
5. JSON Schema `enum` arrays containing URN family strings.
6. YAML lists with URN family names as items.

Concrete locations covered:

- `src/atdd/coach/**` (URN engine, graph utilities, validators, CLI commands)
- `src/atdd/planner/**` (planner validators and schemas)
- `src/atdd/tester/**` (tester validators, schemas, conventions, recipes)
- `src/atdd/coder/**` (coder validators, schemas, conventions, recipes:
  `complexity.recipe.yaml`, `adapter.recipe.yaml`, `design.recipe.yaml`,
  `thinness.recipe.yaml`)
- `src/atdd/cli.py` (top-level argparse tree)
- `.github/workflows/*.yml` (CI configuration)
- `CLAUDE.md` (agent prompt — root-level)
- `plan/**`, `contracts/**`, `telemetry/**` (artifact directories)
- `docs/specs/*.md` (substrate spec — referenced only, not redacted)
- Fixtures under `tests/`, `**/tests/`, `**/fixtures/`

## 3. Findings

| # | Location | Type | Classification | Action |
|---|----------|------|----------------|--------|
| 1 | `src/atdd/coach/utils/graph/edge_validator.py` (constructor + `_suggest_parent`) | `_non_orphan_families` set, `parent_map` dict | (a) registered families subset | Added `security`; documented as opt-in (intentionally curated; not all registered families belong here — `test`/`table`/`migration` would create false positives). |
| 2 | `src/atdd/coach/utils/graph/edge_validator.py` (constructor) | `_root_families` set | (b) URN syntax | Now derived from `URNBuilder.SEGMENT_COUNTS` (count == 1 ⇒ no parent ⇒ root family). |
| 3 | `src/atdd/coach/utils/graph/graph_builder.py` (`to_agent_summary`) | `root_families` set | (b) URN syntax | Now derived from `URNBuilder.SEGMENT_COUNTS`; parity with edge validator. |
| 4 | `src/atdd/coach/utils/graph/graph_builder.py` (`to_dot`) | `family_colors` dict | (c) intentionally closed | Visualization-only; keeps `#FAFAFA` fallback. Audit-trail comment added. |
| 5 | `src/atdd/coach/commands/viz_app.py` | `FAMILY_COLORS`, `FAMILY_ICONS` | (c) intentionally closed | Streamlit visualization; uses `FALLBACK_COLOR` / `"circle"` for unknowns. Audit-trail comment added. |
| 6 | `src/atdd/coach/utils/graph/resolver.py` (`find_all_declarations_single_pass`) | `code_scan_families` set | (c) intentionally closed | Performance fast-path that batches code-tree walks; new families fall through to the YAML scan loop. Audit-trail comment added. |
| 7 | `src/atdd/coach/utils/graph/edge_validator.py` (`validate_edges`) | per-family `if/elif node.family == "X"` branches | (c) intentionally closed | Each family encodes spec §8 containment rules; new families simply skip these checks. Audit-trail comment added at the method docstring. |
| 8 | `src/atdd/coach/utils/graph/urn.py` (`parse_urn`) | per-family `if/elif urn.startswith('X:')` branches | (c) intentionally closed — **documented extension point** | The acceptance criteria explicitly call out `parse_urn` as the place new families add a branch. Audit-trail comment added at the method docstring. |
| 9 | `src/atdd/coach/commands/tests/test_E001_cli_characterization.py:266` | `core_families = [...]` list | (c) intentionally closed | Existence-only assertion ("output mentions ≥6 core families"); not a closed enumeration of all families. No edit needed. |

### Sites considered and ruled out (not findings)

- `src/atdd/coach/utils/graph/urn.py::URNBuilder.PATTERNS` itself, and
  `URNBuilder.SEGMENT_COUNTS` — these **are** the registry of URN syntax;
  iterating them is exactly what (b) prescribes. No edit.
- `src/atdd/coach/utils/graph/resolver.py::ResolverRegistry._register_default_resolvers`
  — explicit list of the resolvers that ship out of the box. New families
  call `registry.register(...)` in tests / extensions; the default list
  exists by design as the "shipped families" manifest.
- `src/atdd/coach/utils/graph/graph_builder.py` `_build_security_edges`,
  per-family edge-builder methods — bespoke spec §8 graph-edge construction;
  new families opt in by adding a builder. Equivalent to finding #7.
- `src/atdd/coach/commands/viz_app.py::EDGE_STYLES_MAP` and
  `TRAIN_CATEGORY_COLORS` — keyed on edge types and train categories,
  not URN families.
- `src/atdd/coach/conventions/issue.convention.yaml` `archetypes:` —
  ATDD lifecycle archetype taxonomy (db, be, fe, contracts, wmbt, wagon,
  train, telemetry, migrations, coach). Some archetypes share names with
  URN families but the enumeration has different semantics
  (issue-classification, not URN-syntax) and an authoritative spec
  (issue.convention.yaml). Out of scope.
- `src/atdd/coach/schemas/{session,project_fields,label_taxonomy}.schema.json`
  — same archetype taxonomy as above, mirrored in JSON Schema for GitHub
  Project v2 fields.
- `src/atdd/coder/validators/test_dead_code_python.py::TEST_DIRS = {"test", "tests"}`,
  similar `{"test", "tests"}` patterns — directory names, not URN families.
- `.github/workflows/atdd-validate.yml` `'atdd-wmbt'` label expressions —
  GitHub label name, not a URN family enumeration.
- `src/atdd/coder/conventions/*.recipe.yaml` `components/`, `tests/` —
  directory references inside ATDD design-system recipes, not URN families.
- `src/atdd/coach/utils/rule_validator_resolver.py::_VALID_ARCHETYPES` —
  ATDD lifecycle archetypes (`coder`/`coach`/`tester`/`planner`); not
  URN families.

## 4. Throwaway extension demo (acceptance criterion)

`src/atdd/coach/utils/graph/tests/test_urn_extension_contract.py` installs a
`theatre:` URN family for the duration of one pytest run via `monkeypatch`:

```python
@pytest.fixture
def theatre_pattern_installed(monkeypatch):
    new_patterns = dict(URNBuilder.PATTERNS)
    new_patterns["theatre"] = r"^theatre:[a-z][a-z0-9-]*$"
    monkeypatch.setattr(URNBuilder, "PATTERNS", new_patterns)

    new_counts = dict(URNBuilder.SEGMENT_COUNTS)
    new_counts["theatre"] = 1
    monkeypatch.setattr(URNBuilder, "SEGMENT_COUNTS", new_counts)
```

The test then verifies the contract:

| Step | Assertion | Result |
|------|-----------|--------|
| (a) Resolver registration | `"theatre" in registry.families` after `registry.register(TheatreResolver(...))` | ✅ pass |
| (b) PATTERNS entry | `URNBuilder.validate_urn("theatre:hamlet", "theatre")` and `validate_grammar(...)` | ✅ pass |
| (b) Wrong segment count | `validate_grammar("theatre:hamlet:act-1")` raises `wrong segment count` | ✅ pass |
| Validators untouched | Orphan check + `validate_edges` + `validate_all` run cleanly on a graph containing `theatre:` nodes (no crashes, no false positives) | ✅ pass |
| CLI untouched | `atdd repo families` iterates `ResolverRegistry.families` — picks up the new family with no argparse edit | ✅ pass |
| Test discovery untouched | `registry.find_all_declarations()` includes `theatre` automatically | ✅ pass |

Full graph test suite (`pytest src/atdd/coach/utils/graph/`): **108 passed**,
including the 6 new contract tests.

## 5. PR references for fixes

All findings #1–#8 above are remediated in the same PR that lands this report.
The diff touches:

- `src/atdd/coach/utils/graph/edge_validator.py` — security family added,
  root families derived from `SEGMENT_COUNTS`, audit-trail comments.
- `src/atdd/coach/utils/graph/graph_builder.py` — root families derived
  from `SEGMENT_COUNTS`, DOT export comment.
- `src/atdd/coach/utils/graph/resolver.py` — `code_scan_families` comment.
- `src/atdd/coach/utils/graph/urn.py` — `parse_urn` extension-point comment.
- `src/atdd/coach/commands/viz_app.py` — visualization-mapping comment.
- `src/atdd/coach/utils/graph/tests/test_urn_extension_contract.py` —
  new test module (the throwaway demo).
- `docs/urn-prefix-audit-2026.md` — this report.
- `.atdd/manifest.yaml` — register issue #421.

## 6. Conclusion

Three closed enumerations needed remediation (`_non_orphan_families` to add
`security`; `_root_families` and the duplicate `root_families` in
`graph_builder` to derive from `URNBuilder.SEGMENT_COUNTS`). All other
sites were intentionally closed (visualization, performance fast-paths,
spec-driven per-family branches) and have been anchored with comments
pointing back to this report.

The throwaway `theatre:` extension test confirms the substrate contract:
**adding a new URN family touches only `resolver.py`, one `PATTERNS` entry,
one `parse_urn` branch, and (optionally) a builder method.** No validators,
CLI subcommand definitions, test-discovery code, or graph-builder code
require edits.
