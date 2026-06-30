"""Dirty module — each function trips exactly one complexity threshold.

  classify        -> cyclomatic complexity > 10
  deep_nest       -> nesting depth > 4
  long_function   -> function length (LOC) > 50
  many_params     -> parameter count > 6
  cognitive_heavy -> cognitive complexity > 15
"""


def classify(value, mode, flag, kind):
    result = 0
    if value > 0 and mode == "a":
        result = 1
    elif value > 1 or flag:
        result = 2
    elif value > 2:
        result = 3
    for i in range(value):
        if i % 2 == 0 and flag:
            result += i
    while result < 100 or kind == "x":
        result += 1
    try:
        result = result / value
    except ZeroDivisionError:
        result = 0
    return result


def deep_nest(data):
    if data:
        for a in data:
            if a:
                for b in a:
                    if b:
                        return b
    return None


def long_function():
    x0 = 0
    x1 = 1
    x2 = 2
    x3 = 3
    x4 = 4
    x5 = 5
    x6 = 6
    x7 = 7
    x8 = 8
    x9 = 9
    x10 = 10
    x11 = 11
    x12 = 12
    x13 = 13
    x14 = 14
    x15 = 15
    x16 = 16
    x17 = 17
    x18 = 18
    x19 = 19
    x20 = 20
    x21 = 21
    x22 = 22
    x23 = 23
    x24 = 24
    x25 = 25
    x26 = 26
    x27 = 27
    x28 = 28
    x29 = 29
    x30 = 30
    x31 = 31
    x32 = 32
    x33 = 33
    x34 = 34
    x35 = 35
    x36 = 36
    x37 = 37
    x38 = 38
    x39 = 39
    x40 = 40
    x41 = 41
    x42 = 42
    x43 = 43
    x44 = 44
    x45 = 45
    x46 = 46
    x47 = 47
    x48 = 48
    x49 = 49
    x50 = 50
    return x50


def many_params(alpha, beta, gamma, delta, epsilon, zeta, eta):
    return alpha + beta + gamma + delta + epsilon + zeta + eta


def cognitive_heavy(items):
    total = 0
    for item in items:
        if item > 0:
            if item % 2 == 0:
                for sub in range(item):
                    if sub and total:
                        total += sub
    return total
