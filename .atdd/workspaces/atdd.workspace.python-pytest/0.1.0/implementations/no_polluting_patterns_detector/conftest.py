# The fixtures/ tree is the CODE-UNDER-INSPECTION (``test_*.py`` files the
# detector reads as text), NOT this detector's own pytest suite. The dirty fixture
# intentionally contains shared-git-state pollution patterns; keep pytest from
# collecting and executing them.
collect_ignore_glob = ["fixtures/*", "fixtures/**"]
