"""Idempotent process-local evidence index for deterministic tests."""

from ...domain.intelligence import Observation, PersistenceState
from ...domain.media import Source


class InMemoryEvidenceIndex:
    def __init__(self) -> None:
        self._observations: dict[str, Observation] = {}

    def upsert(self, observation: Observation) -> None:
        existing = self._observations.get(observation.observation_id)
        if existing is not None and existing != observation:
            raise ValueError("index identifier has different content")
        self._observations[observation.observation_id] = observation

    def search(self, source: Source, question: str) -> tuple[Observation, ...]:
        terms = {term.strip("?.,").lower() for term in question.split() if len(term) > 3}
        return tuple(
            observation for _, observation in sorted(self._observations.items())
            if observation.context.source == source.reference
            and terms.intersection(observation.value.lower().split())
        )

    def state(self, window_id: str) -> PersistenceState:
        indexed = any(
            link.evidence_window_id == window_id
            for observation in self._observations.values()
            for link in observation.context.evidence
        )
        return PersistenceState.INDEXED if indexed else PersistenceState.PENDING

    def count(self) -> int:
        return len(self._observations)


__all__ = ["InMemoryEvidenceIndex"]
