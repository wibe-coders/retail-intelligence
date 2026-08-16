"""Budget-enforcing adapter for RT-VLM caption inference."""

from ...inference_budget import InferenceBudget, evaluate_inference_budget
from ...ports.caption import (
    CaptionClient,
    CaptionPreprocessor,
    CaptionRequest,
    CaptionStageOutcome,
    CaptionStageState,
)


class RTVLMCaptionAdapter:
    """Admit only planned and realized model inputs within the token limits."""

    def __init__(self, preprocessor: CaptionPreprocessor, client: CaptionClient) -> None:
        self._preprocessor = preprocessor
        self._client = client

    def caption(self, request: CaptionRequest) -> CaptionStageOutcome:
        selected_count = min(len(request.frames), request.selected_frame_count)
        if selected_count == 0:
            return CaptionStageOutcome(CaptionStageState.GAP, None, None, "no_source_frames")

        selected_frames = self._select_evenly_spaced(request.frames, selected_count)
        planned_budget = evaluate_inference_budget(request.width, request.height, selected_count)
        if not planned_budget.accepted:
            return self._stopped_outcome(request, planned_budget)

        prepared = self._preprocessor.prepare(selected_frames, request.width, request.height)
        if prepared.selected_frame_count == 0:
            return CaptionStageOutcome(CaptionStageState.GAP, None, None,
                                       "preprocessing_produced_no_frames")
        if prepared.selected_frame_count > selected_count:
            return CaptionStageOutcome(CaptionStageState.PARTIAL, planned_budget, None,
                                       "preprocessor_duplicated_frames")

        inference_budget = evaluate_inference_budget(
            prepared.width, prepared.height, prepared.selected_frame_count
        )
        if not inference_budget.accepted:
            return self._stopped_outcome(request, inference_budget)
        response = self._client.infer(prepared)
        state = (CaptionStageState.COMPLETE if selected_count == request.selected_frame_count
                 else CaptionStageState.PARTIAL)
        return CaptionStageOutcome(state, inference_budget, response, None)

    @staticmethod
    def _select_evenly_spaced(frames: tuple[object, ...], count: int) -> tuple[object, ...]:
        if count == len(frames):
            return frames
        if count == 1:
            return (frames[0],)
        last_index = len(frames) - 1
        return tuple(frames[index * last_index // (count - 1)] for index in range(count))

    @staticmethod
    def _stopped_outcome(request: CaptionRequest, budget: InferenceBudget) -> CaptionStageOutcome:
        state = (CaptionStageState.PARTIAL
                 if len(request.frames) < request.selected_frame_count
                 else CaptionStageState.REJECTED)
        return CaptionStageOutcome(state, budget, None, budget.rejection_reason)


__all__ = ["RTVLMCaptionAdapter"]
