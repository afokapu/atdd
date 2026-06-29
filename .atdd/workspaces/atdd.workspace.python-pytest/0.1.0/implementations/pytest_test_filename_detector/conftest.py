# The fixtures/ tree is the CODE-UNDER-INSPECTION (test-shaped files the detector
# reads as text), NOT this detector's own pytest suite. Keep pytest from
# collecting them as real tests — the clean fixture is intentionally a runnable
# `test_*.py` and the dirty fixtures intentionally carry `def test_*` bodies under
# non-collectable names.
collect_ignore_glob = ["fixtures/*", "fixtures/**"]
