# The fixtures/ tree is the CODE-UNDER-INSPECTION (acceptance YAML + metric
# modules the detector reads as text), NOT this detector's own pytest suite. Keep
# pytest from collecting the fixture metric modules.
collect_ignore_glob = ["fixtures/*", "fixtures/**"]
