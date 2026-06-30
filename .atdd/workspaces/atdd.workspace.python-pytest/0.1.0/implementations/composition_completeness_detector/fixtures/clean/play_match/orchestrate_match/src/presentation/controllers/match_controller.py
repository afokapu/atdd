from application.play_match_use_case import PlayMatchUseCase
from integration.match_repository import MatchRepository


_repository = None
_use_case = None


def set_match_repository(repository: MatchRepository) -> None:
    global _repository
    _repository = repository


def set_match_use_case(use_case: PlayMatchUseCase) -> None:
    global _use_case
    _use_case = use_case
