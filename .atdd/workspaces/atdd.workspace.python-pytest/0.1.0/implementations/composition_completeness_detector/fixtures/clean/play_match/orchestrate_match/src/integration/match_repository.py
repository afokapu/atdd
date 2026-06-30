from domain.match import Match


class MatchRepository:
    def load(self) -> Match:
        return Match("finals")
