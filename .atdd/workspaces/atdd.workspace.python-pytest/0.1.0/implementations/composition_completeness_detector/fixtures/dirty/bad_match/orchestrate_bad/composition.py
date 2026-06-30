# DIRTY: imports the presentation setters but NEVER CALLS them, so the
# presentation layer is not reached from the composition root -> a
# coder.refactor.composition-root violation (presentation missing).
from application.play_match_use_case import PlayMatchUseCase
from integration.match_repository import MatchRepository
from presentation.controllers.match_controller import (
    set_match_repository,
    set_match_use_case,
)


def compose() -> PlayMatchUseCase:
    repository = MatchRepository()
    return PlayMatchUseCase(repository)
