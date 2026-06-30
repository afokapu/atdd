from domain.match import Match
from integration.match_repository import MatchRepository


class PlayMatchUseCase:
    def __init__(self, repository: MatchRepository) -> None:
        self.repository = repository

    def execute(self) -> Match:
        return self.repository.load()
