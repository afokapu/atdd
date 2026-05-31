"""``atdd.train`` — stateful train-runner orchestration layer.

This package owns runs, events, persistence, resume, and wave concurrency
(docs/coach-decomposition.md §3.1, §3.2). It depends inward on ``atdd.coach.core``
(pure policy) and on the runtime/integration adapters; it MUST NOT be imported by
``atdd.coach.core`` (enforced by the import-discipline test, §3.3 / §10.2).

Child 3 (#890) lands the *contract* surface only — the ``PersistenceStore``
Protocol, the run/event types, and the events.jsonl schema constants. Concrete
implementations (``JsonlPersistenceStore``, ``materialize_evidence``) ship in
Child 7 (#894).
"""
