# The fixtures/ tree is the CODE-UNDER-INSPECTION (consumer interlocking YAML + Station Master +
# InterlockingRunner runtime + e2e trace tests the detector reads as text), NOT this implementation's
# own pytest suite. The pass/fail fixtures intentionally carry `def test_*` bodies and import a
# `trains.runtime` module that does not exist here — keep pytest from collecting them as real tests.
collect_ignore_glob = ["fixtures/*", "fixtures/**"]
