# DIRTY: an application-layer file that NO presentation or composition consumer
# imports -> a coder.refactor.composition-consumer violation (0 consumers). It
# imports domain so the domain layer still has a valid consumer.
from domain.match import Match


class OrphanUseCase:
    def run(self) -> Match:
        return Match("orphan")
