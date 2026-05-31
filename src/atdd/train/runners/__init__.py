"""TrainRunner implementations (docs/coach-decomposition.md §3.1, §7).

``jsonl`` ships the default/first ``JsonlTrainRunner`` (Child 8 / #895). The
``temporal`` and ``langgraph_review`` names are reserved (§7.2 / §7.3) and are
deliberately NOT implemented — the CLI raises ``NotImplementedError`` for them.
"""
