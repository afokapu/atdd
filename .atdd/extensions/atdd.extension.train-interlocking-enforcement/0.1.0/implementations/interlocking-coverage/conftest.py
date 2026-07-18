# The fixtures/ tree is the CODE-UNDER-INSPECTION (consumer interlocking YAML +
# e2e test files the detector reads as text), NOT this implementation's own pytest
# suite. The dirty/clean e2e fixtures intentionally carry `def test_*` bodies and
# `# URN: test:` headers under a consumer layout and import a `trains.runtime`
# module that does not exist here — keep pytest from collecting them as real tests.
collect_ignore_glob = ["fixtures/*", "fixtures/**"]
