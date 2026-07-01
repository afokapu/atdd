"""RED fixture root: imports service but NOT orphan -> orphan is unreachable."""
from service import run


def wire():
    return run
