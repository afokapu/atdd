"""Clean: Match entity implemented in Python (parity with Dart + contract)."""


class Match:
    def __init__(self, id: str, score: int):
        self.id = id
        self.score = score
