"""Money value object — a tiny, well-formed domain type."""


class Money:
    # amount is stored in minor units (cents)
    def __init__(self, cents):
        self.cents = cents

    def add(self, other):
        return Money(self.cents + other.cents)
