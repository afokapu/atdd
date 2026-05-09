# Coach v9 Validator Invocation Contract

> **Status:** Frozen at C0 (issue #483).
>
> **Sibling contracts:**
> [`runtime-layout.md`](./runtime-layout.md) ·
> [`event-semantics.md`](./event-semantics.md) ·
> [`validator-result.schema.json`](./validator-result.schema.json) ·
> [`risk-score.schema.json`](./risk-score.schema.json)

This document is the subprocess contract between the coach state
machine (#J3) and the substrate's pytest plugin. Track M (validator
dispatch) and Track J (state machine) MUST agree on every clause here;
deviation is a coordination break, not a tuning knob.

---

## 1. Pytest CLI flag set

The coach invokes `python -m pytest` per phase with the following base
flag set:

```sh
python -m pytest \
    --tb=short \
    -q \
    --strict-markers \
    -p atdd.coach.plugins.violation_collector \
    -p atdd.coach.plugins.diagnostics \
    --rootdir=<repo-root> \
    <selected-validator-paths>
```

Per-flag rationale:

| Flag | Why |
|------|-----|
| `--tb=short` | Tracebacks fit in the JSONL output line; longer forms break log parsers. |
| `-q` | Coach reads from the violation-collector plugin, not stdout — quiet pytest avoids drowning the log. |
| `--strict-markers` | Unknown markers are a coordination failure (a track using an unregistered marker), and MUST fail loud. |
| `-p atdd.coach.plugins.violation_collector` | Forces the violation-collector plugin to load even with autoload disabled (see §2). |
| `-p atdd.coach.plugins.diagnostics` | Loads the diagnostics plugin (timing, env capture) for the same reason. |
| `--rootdir=<repo-root>` | Pin the pytest rootdir so the coach is independent of the cwd it was launched from. |

The `<selected-validator-paths>` are computed by the coach's per-phase
dispatch (see §3); the coach passes explicit paths rather than relying
on `testpaths` so the dispatch decision is auditable.

---

## 2. Plugin autoload policy

The coach sets:

```sh
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
```

**Rationale.** Autoload makes the validator subprocess implicitly
inherit any `pytest-*` plugin installed in the consumer environment.
That is unsafe for the coach because:

1. **Reproducibility.** Two consumer repos with different installed
   plugin sets would produce different validator results — the coach's
   risk score would not be portable.
2. **Plugin conflicts.** A consumer with `pytest-mock` shadows fixtures
   the substrate plugin owns; with autoload off, the coach loads only
   what it explicitly opts into via `-p ...` (see §1).
3. **Failure surface.** An autoloaded plugin that crashes at
   `pytest_configure` exits the subprocess before the violation
   collector can flush — a pure plumbing failure that looks like a
   validator failure to the coach gate.

The trade-off — manually opting in via `-p atdd.coach.plugins.*` for
every coach-managed plugin — is the price for a deterministic
validator contract.

---

## 3. Per-phase timeout defaults and override mechanism

Validators run under per-phase timeouts. The defaults are tuned for
the dispatch-set size at each phase (RED is small; REFACTOR sweeps the
whole repo and is much larger).

| Phase | Default timeout (seconds) |
|-------|---------------------------|
| RED | 60 |
| GREEN | 180 |
| SMOKE | 300 |
| REFACTOR | 600 |

**Override mechanism.** Per-phase defaults can be overridden two ways:

1. **Env var.** `ATDD_VALIDATOR_TIMEOUT_<PHASE>=<seconds>` — e.g.
   `ATDD_VALIDATOR_TIMEOUT_REFACTOR=900`. Empty / unset means "use the
   default above". Negative values are rejected and the coach refuses
   to start the run.
2. **Config key.** `coach.validator.timeout.<phase>` in
   `.atdd/config.yaml` (lower-case phase). Resolution order is
   env-var > config > default, so a CI-only env-var bump cannot be
   accidentally locked in by a stray config edit.

A timeout firing kills the subprocess group with `SIGTERM`, waits 5
seconds, then `SIGKILL`s anything still alive. The coach records a
`validator_timeout` outcome in the run manifest.

---

## 4. Retry policy — subprocess crash vs test failure

These two failure modes carry different signal handling and the coach
MUST distinguish them at every dispatch site.

### 4.1 Test failure

A "test failure" is a non-zero pytest exit code where the
violation-collector plugin produced records (i.e. pytest itself ran
and the failure surface is one or more validators reporting violations).

**Retry policy.** **No retry.** Test failures are coach-visible signal
and feed directly into the disposition gate. Retrying would mask
transient determinism bugs (one of the highest-cost failure classes
this contract was written to surface).

**Detection.** Pytest exit code in `{1, 2, 3, 4}` (test failures,
collection errors, internal errors, usage errors) AND
`violations.jsonl` is non-empty.

### 4.2 Subprocess crash

A "subprocess crash" is the validator process dying *outside* the
test path — segfault (`SIGSEGV`), hard timeout, OOM kill, or an
exception inside a pytest hook before the violation-collector plugin
flushed.

**Retry policy.** **One retry**, with full subprocess restart and
plugin reload. A second crash on the same dispatch unit fails the
coach run with a `subprocess_crash` outcome rather than a violation
report.

**Detection.** Any of:
- Exit was a fatal signal (negative exit code on POSIX, where
  `os.WIFSIGNALED(status)` is True);
- Pytest exit code `{5, 6}` (no tests collected, usage errors with no
  collection) AND `violations.jsonl` is empty;
- Coach-side timeout (§3) fired before pytest exited.

### 4.3 Why the distinction matters

The two policies use **different signal handling**: test failure is a
clean exit from pytest with structured records; subprocess crash is
out-of-band signal-driven termination. Conflating them — retrying on
test failure or failing-on-first-crash — corrupts the risk score in
ways that surface only at the integration step. C0 freezes the
distinction so #J3 and #M3 cannot drift.

---

## 5. Env-var passthrough

The coach passes the following env vars to validator subprocesses,
verbatim from its own environment (no transformation, no defaulting):

| Var | Why |
|-----|-----|
| `PATH` | Locating the python interpreter and any helper binaries. |
| `HOME` | Some validators read user-level config; required for stable resolution. |
| `PYTHONPATH` | Honors the consumer repo's `pythonpath` if set. |
| `PYTEST_DISABLE_PLUGIN_AUTOLOAD` | Forwarded to enforce the §2 policy in the child. |
| `ATDD_VALIDATOR_TIMEOUT_*` | Honors per-phase overrides (§3). |
| `ATDD_RUN_ID` | Run-scoped correlation id; lets the violation-collector tag records. |
| `CI` | Some validators relax behavior outside CI; the env var must reach the child. |
| `GITHUB_TOKEN` | Forwarded only if the validator's manifest opts in (security: most validators MUST NOT see it). |
| `LANG`, `LC_ALL` | Locale; YAML/JSON parsers can otherwise interpret bytes inconsistently. |

Every other env var is **dropped**. This is deliberate: the coach
runs with whatever environment cmux/CI hands it, and we do not want
arbitrary ambient state to leak into the validator subprocess.

---

## 6. Summary checklist for implementers

Before opening a PR that touches the validator dispatch path, confirm:

- [ ] Pytest CLI flags match §1 verbatim (no implicit additions in
      the dispatch wrapper).
- [ ] `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` is set on the subprocess
      env (§2).
- [ ] Per-phase timeouts match §3 unless an explicit override path is
      added — and the override path is documented.
- [ ] Subprocess-crash retry is distinct from test-failure retry
      (§4); the two are not collapsed into a generic "retry on
      failure" branch.
- [ ] Env-var passthrough is whitelisted, not blacklisted (§5).
