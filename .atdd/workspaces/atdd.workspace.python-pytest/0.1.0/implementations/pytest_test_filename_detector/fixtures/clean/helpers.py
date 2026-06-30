"""A non-test helper module. No `# URN: test:` header and no top-level `def
test_*`, so it is NOT an intended test and is never flagged even though its name
is not pytest-collectable."""


def build_user(name):
    return {"name": name}
