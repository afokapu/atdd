# The fixtures/ tree is the CODE-UNDER-INSPECTION (``test_*.py`` files the
# detector reads as text), NOT this detector's own pytest suite. The dirty fixture
# intentionally carries self-skip mechanisms; keep pytest from collecting them
# (a collected pytest.skip would simply skip — exactly the masquerade this rule
# guards against — and pollute the run summary).
collect_ignore_glob = ["fixtures/*", "fixtures/**"]
