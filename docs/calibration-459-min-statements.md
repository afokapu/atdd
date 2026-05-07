# Calibration: `MIN_DUPLICATE_STATEMENTS` for `coder.refactor.quality-duplication`

Phase 1 deliverable for issue #459 — replace the line-based algorithm in
`src/atdd/coder/validators/test_quality_metrics.py::find_duplicate_code_blocks`
with an AST-based statement-window matcher (Option C).

## Methodology

Calibrate `min_statements` against the toolkit's own `src/atdd/` tree.
For each candidate value, run `extract_fragments` (from `test_duplication_detector.py`)
and count cross-file duplicate pairs (one finding per `(file1, file2, hash)` tuple).
Compare against the existing line-based detector at `MAX_DUPLICATE_LINES = 5`.

**Corpus:** `src/atdd/` — 130 non-test Python files (toolkit-self).
**Excluded:** `*/test*/`, `test_*.py`, `__pycache__`.

## Results

### Line-based baseline (current production)

| Scope | Violations | Runtime |
|-------|-----------:|--------:|
| `files[:50]` cap | 115 | 0.72 s |
| Full tree (130 files) | 177 | 22.20 s |

The `[:50]` cap exists because line-based comparison is O(N²·L²) — full-tree runtime crosses the budget envelope.

### AST-based sweep — full src/atdd/ (no cap)

| `min_statements` | Pairs flagged | Runtime |
|-----------------:|--------------:|--------:|
| 3 | 529 | 1.57 s |
| **5** | **69** | **1.91 s** |
| 7 | 11 | 2.14 s |
| 10 | 0 | 2.31 s |

### AST-based sweep — `files[:50]` cap (parity with current scope)

| `min_statements` | Pairs flagged | Runtime |
|-----------------:|--------------:|--------:|
| 3 | 110 | 0.26 s |
| **5** | **36** | **0.30 s** |
| 7 | 9 | 0.32 s |
| 10 | 0 | 0.33 s |

## Decisions

### `MIN_DUPLICATE_STATEMENTS = 5`

Picked for parity-or-better signal against the line-based baseline:

- At full tree: 69 AST findings vs 177 line-based — the AST run preserves real
  duplication signal while shedding the lexically-similar-but-structurally-different
  noise (re-export blocks, repeated `from X import` patterns) that drove issue #459.
- `min_statements = 3` is too noisy (529 findings — trivial three-statement windows match across many files).
- `min_statements = 7` and `10` are too lenient and lose real findings (the existing toolkit-self baseline of 60+ items collapses to 11 and 0 respectively).
- `5` is also the value used by the sister detector (`coder.duplication.no-intra-layer-code-python`),
  keeping the two converged-algorithm rules calibrated to the same threshold.

### Drop the `python_files[:50]` cap

The cap was put in place as a perf safeguard for the O(N²·L²) line-based loop.
The AST detector parses each file once, then performs O(N) hash-map insertion and lookup —
full-tree runtime at `min_statements = 5` is **1.91 s**, well under any reasonable budget.

The cap is also non-deterministic (depends on `rglob` enumeration order),
so violations and non-violations swap into the sample as files are added or
renamed. Removing it makes the scope policy explicit: the rule scans every
non-test Python file in the configured tree, every run.

## Rename-insensitive semantic shift

AST normalization maps every `Name` to `"VAR"` and constants to `0`/`""`.
Two structurally-identical functions with different identifier names are now
flagged as duplicates where they previously weren't. Phase 2 includes a fixture
test that locks this in (so the new semantics aren't silently weakened later).

## Phase 3 — self-compliance regression on `src/atdd/`

After Phase 2 landed, ran the new `find_duplicate_code_blocks` against the
toolkit's own `src/atdd/` tree (no cap, 130 non-test files).

| Algorithm | Scope | Violations |
|-----------|-------|-----------:|
| Line-based (current production) | `files[:50]` cap | 115 |
| Line-based (current production) | full tree | 177 |
| **AST (Option C)** | **full tree, `min_statements = 5`** | **48** |

**Structural breakdown of the 48 AST findings:**

- Pairs involving `__init__.py`: **0**  (the originally-reported false-positive
  shape from issue #459 is fully cleared on the toolkit's own tree).
- Same-directory pairs: 34  (mostly intra-module helpers and validators
  scanning similar AST shapes — these are real signal worth review).
- Cross-directory pairs: 14.

**Per-subsystem distribution:**

| Subsystem pair | Pairs |
|---|---:|
| `tester ↔ tester` | 19 |
| `coach ↔ coach` | 17 |
| `tester ↔ coach` | 6 |
| `coder ↔ coach` | 3 |
| `coder ↔ coder` | 2 |
| `runners ↔ runners` | 1 |

The toolkit's existing `coder.refactor.quality-duplication` rule on this
repo is effectively a no-op (`find_python_files()` resolves to `python/`
which doesn't exist in toolkit-self), so the existing baseline file does not
constrain phase-2 vs phase-3 numbers. The relevant comparison is the table
above: false-positives gone (0 `__init__.py` pairs vs. originally 13 in the
reproducer), real findings preserved-or-reduced (48 < 115 net).

`atdd validate coder --local` still passes (the test skips on toolkit-self
because there is no `python/` directory). Consumers like `jel-ledger` whose
trees do live under `python/` will see the false-positive clearance directly.
