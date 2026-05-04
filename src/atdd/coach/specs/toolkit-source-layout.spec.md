# Toolkit Source Layout SPEC

`SPEC-COACH-PKG-LAYOUT-0001..0004`

This SPEC governs how toolkit code locates its own assets and detects its
own version. It exists because the same anti-pattern shipped three times in
two days (#341, #352, #367) — each silent until the alternate execution
mode was exercised, each costing 30+ minutes to root-cause.

The detector that enforces this SPEC lives at
`src/atdd/coach/validators/test_toolkit_source_layout_assumptions.py`. The
machine-readable convention is
`src/atdd/coach/conventions/source-layout.convention.yaml`.

---

## The three layout shapes the toolkit must support

The atdd toolkit can run from three execution shapes, and code that
hard-codes assumptions about any one of them breaks the others silently:

| Shape | Where atdd lives | When it's used |
|-------|------------------|----------------|
| **Toolkit-self repo** | `<repo>/src/atdd/` | Active development, `PYTHONPATH=src python3 -m atdd ...` |
| **Editable install** | `<repo>/src/atdd/` (with `.pth` or `pip install -e .`) | Contributor laptops |
| **Wheel install** | `<site-packages>/atdd/` | Consumer projects, CI consumer-side, ATDD release |

Code that uses `find_repo_root() + "src/atdd/..."` works in shapes 1–2 and
fails in 3. Code that calls bare `version("atdd")` works in shape 3 and
fails in shape 1 (CI's exact setup, since the workflow installs deps but
runs atdd from `src/`). Code that uses `Path(atdd.__file__).parent` works
in all three.

---

## SPEC-COACH-PKG-LAYOUT-0001 — Pattern A: toolkit-self layout assumption

A rule violation is any expression where:

- a `Call` to `find_repo_root` (directly, or wrapped in `or` /
  `Path(...)`) appears as the leftmost operand of a left-deep `BinOp(Div)`
  chain, AND
- the chain's string-literal segments include `"src"` followed by
  `"atdd"` (or a single segment containing `"src/atdd"`).

Conforming shapes:

```python
# bad — toolkit-self only
SCHEMA = find_repo_root() / "src" / "atdd" / "coach" / "schemas" / "config.schema.json"
SCHEMA = (repo_root or find_repo_root()) / "src/atdd/coach/conventions"

# good — package-relative, works in all three layouts
import atdd
ATDD_PKG_DIR = Path(atdd.__file__).resolve().parent
SCHEMA = ATDD_PKG_DIR / "coach" / "schemas" / "config.schema.json"

# good — find_repo_root for *consumer* paths is fine
TRAINS = find_repo_root() / "plan" / "_trains.yaml"
PYTHON_TESTS = find_repo_root() / "python" / "tests"
```

`find_repo_root()` itself is not deprecated. The rule narrowly forbids the
combination `find_repo_root() / "src/atdd/..."` — descending *into* the
toolkit through the consumer's repo root.

---

## SPEC-COACH-PKG-LAYOUT-0002 — Pattern B: install-detection assumption

A rule violation is any `Call` where:

- the callee resolves to a name in `{version, pkg_version}` or an attribute
  access ending in `version` (e.g. `importlib.metadata.version`), AND
- the first argument is the string literal `"atdd"`, AND
- the call site is **not** enclosed by a `try` whose handlers catch
  `PackageNotFoundError` or `Exception`.

Conforming shapes:

```python
# bad — raises PackageNotFoundError when atdd runs from source
APP_VERSION = version("atdd")
APP_VERSION = pkg_version("atdd")
APP_VERSION = importlib.metadata.version("atdd")

# good — single source of truth, defined in src/atdd/__init__.py
from atdd import __version__
APP_VERSION = __version__

# good — version() of a *different* package is unaffected
PYTEST_VERSION = version("pytest")
```

The single legitimate `version("atdd")` call site is `src/atdd/__init__.py`,
which wraps it in the canonical try/except:

```python
# src/atdd/__init__.py — the *one* place this pattern is allowed
from importlib.metadata import PackageNotFoundError, version
try:
    __version__ = version("atdd")
except PackageNotFoundError:
    __version__ = "0.0.0"
```

The detector excludes `__init__.py` files from scanning, so the canonical
wrapper is exempt by file-name. Inline try/except wrappers anywhere else
(e.g. inside a function body) are also exempt because the AST walker
checks for an enclosing `Try` ancestor whose handlers catch
`PackageNotFoundError` or bare `Exception`.

---

## SPEC-COACH-PKG-LAYOUT-0003 — Suppression

Inline suppression on the offending line silences a single violation:

```python
root = find_repo_root() / "src" / "atdd" / "coach" / "commands" / "tests"  # atdd:suppress(coach.source-layout.toolkit-code-must-not)
```

Suppressions are intended for code paths that are toolkit-self-only by
design (e.g. autofix routines that target the toolkit's own test sources
and fall through silently in pip-installed consumers). Each suppression
should be paired with a comment justifying the exception.

The suppression grammar follows
[`logging.convention.yaml::coder.logging.coach-silent-swallow`](../conventions/../coder/conventions/logging.convention.yaml)
and the `rule-id.spec.md` substrate (#357 + #340).

---

## SPEC-COACH-PKG-LAYOUT-0004 — Limits and known exclusions

The detector is intentionally conservative. The following shapes are **not**
flagged today:

- **Variable indirection.** `REPO_ROOT = find_repo_root()` followed many lines
  later by `REPO_ROOT / "src" / "atdd"` is missed because the AST walker does
  not perform data-flow analysis. The risk is judged low — the canonical
  recipe (`Path(atdd.__file__).parent`) is so much shorter that the bad
  shape is rarely worth typing across two statements.
- **Cross-language detection.** Frontend / TypeScript code has its own
  resolver patterns and is out of scope. The toolkit-self codebase is
  Python only.
- **Auto-fix.** Detection only. Past 3 instances were already fixed by
  hand; future occurrences surface at PR time and can be either
  refactored to the canonical recipe or pre-suppressed with a
  justification comment.

---

## Incident references

| Issue | Pattern | Symptom | Root-cause time |
|-------|---------|---------|-----------------|
| #341  | A (PATH for argv0) | `subprocess.run(['pytest', ...])` failed when pytest wasn't on PATH (CI ran with `PYTHONPATH=src` only) | ~30 min |
| #352  | B | `pkg_version("atdd")` in `cli.py:234` raised `PackageNotFoundError` from source; stderr was empty so CI silently failed with rc=1 | ~30 min |
| #367  | A | `find_repo_root() / "src" / "atdd"` in three coach validators raised `FileNotFoundError` in pip-installed consumers | ~20 min |

After three instances, this validator was added in #368 to convert "category
of past bugs" into "automated guard against future occurrences."
