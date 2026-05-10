"""Substrate-aware observer rule package.

The toolkit-shipped observer rules live under ``rules/`` and are loaded
by ``atdd.coach.commands.observer.RuleRegistry`` against a worktree
``ObservedInput``. The predicates that back the substrate-aware
trigger types (rules 10/11/12/17 per spec §8.3) live in
:mod:`atdd.coach.observer.predicates`.
"""
