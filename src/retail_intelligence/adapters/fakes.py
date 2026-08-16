"""Deterministic model adapters used by cloud acceptance tests."""

from ..domain.intelligence import Observation
from ..domain.media import Source


class FixedCaptionModel:
    def __init__(self, caption: str) -> None:
        self._caption = caption

    def caption(self, source: Source, window_id: str) -> str:
        return self._caption


class EvidenceOnlyAnswerModel:
    def answer(self, question: str, observations: tuple[Observation, ...]) -> str | None:
        if not observations:
            return None
        return observations[0].value


__all__ = ["EvidenceOnlyAnswerModel", "FixedCaptionModel"]
