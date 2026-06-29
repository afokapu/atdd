"""Clean module — every function stays under all five complexity thresholds."""


def add(a, b):
    return a + b


def greet(name):
    if name:
        return f"hello {name}"
    return "hello"


def total(values):
    running = 0
    for value in values:
        running += value
    return running
