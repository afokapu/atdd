# URN: test:demo:dirty:UNIT-001-git-ops-mutate-shared-state
# Phase: GREEN
"""RED fixture: two Wave-12 contamination patterns that mutate shared git state
outside tmp_path scope. The detector emits TWO raw violations; under the strict
disposition any unsuppressed violation -> FAIL.

  - bare-init with cwd=os.getcwd()                  -> bare-init-bad-cwd
  - core.bare config with no -C and no cwd=          -> core-bare-unscoped
"""
import os
import subprocess


def test_bare_init_bad_cwd():
    # BUG: bare repo init scoped to the process cwd contaminates shared git state.
    subprocess.run(["git", "init", "--bare", "/tmp/test"], cwd=os.getcwd())


def test_core_bare_unscoped(tmp_path):
    # BUG: no -C flag, no cwd= — the core.bare mutation escapes tmp_path entirely.
    subprocess.run(["git", "config", "core.bare", "true"])
