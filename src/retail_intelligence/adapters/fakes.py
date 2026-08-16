"""Deterministic model adapters used by cloud acceptance tests."""

from ..domain.intelligence import Observation
from ..domain.media import Source
from ..pipelines.vertical_slice import CaptionModelResult


class FixedCaptionModel:
    def __init__(
        self,
        caption: str,
        model: str = "caption-model",
        model_version: str = "fixture-v1",
        vendor_output_reference: str = "fixture://caption/one",
    ) -> None:
        self._caption = caption
        self._model = model
        self._model_version = model_version
        self._vendor_output_reference = vendor_output_reference
        self.call_count = 0

    def caption(self, source: Source, window_id: str) -> CaptionModelResult:
        self.call_count += 1
        return CaptionModelResult(
            self._caption,
            self._model,
            self._model_version,
            self._vendor_output_reference,
        )


class EvidenceOnlyAnswerModel:
    def answer(self, question: str, observations: tuple[Observation, ...]) -> str | None:
        if not observations:
            return None
        return observations[0].value


__all__ = ["EvidenceOnlyAnswerModel", "FixedCaptionModel"]
