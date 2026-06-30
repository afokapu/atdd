# The fixtures/ tree is the CODE-UNDER-INSPECTION (smoke-shaped ``test_*.py``
# files the detector reads as text), NOT this detector's own pytest suite. Keep
# pytest from collecting them as real tests — they intentionally contain
# collaborator substitutions and assert-free smoke bodies.
collect_ignore_glob = ["fixtures/*", "fixtures/**"]
