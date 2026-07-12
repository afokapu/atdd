# URN: component:enforce-binding-plan:run-binding-plan:backend:domain
# Runtime: python
# Purpose: Lock-driven consumer enforcement runner (issue #1238). Reads
#          binding.lock.yaml, resolves each bound convention's workspace
#          provider, subprocesses it over the consumer's code, bridges the raw
#          v1.1 violation JSON through a non-raising disposition verdict to a
#          single aggregate process exit code.
"""``atdd enforce`` — the lock-driven extension enforcement runner (#1238).

A pure CONSUMER of the installed substrate. It never imports a workspace
provider; the only contract with a provider is "run its ``cli/scan.py``, read
the RAW v1.1 violation JSON off stdout" (boundary discipline, V5 / D-1).

See :mod:`atdd.enforce.runner` for the pipeline and :mod:`atdd.enforce.cli` for
the argv surface + exit-code mapping (0 pass / 1 fail / 2 usage).
"""
from __future__ import annotations
