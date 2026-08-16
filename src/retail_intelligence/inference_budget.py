"""Admission checks for RT-VLM visual-token budgets."""

from dataclasses import dataclass
from typing import Literal


MIN_VISUAL_TOKENS = 4_096
MAX_VISUAL_TOKENS = 16_384
PATCH_SIZE = 32
TEMPORAL_STRIDE = 2

RejectionReason = Literal["below_minimum", "above_maximum"]


@dataclass(frozen=True, slots=True)
class InferenceBudget:
    """The immutable result of evaluating one realized model input."""

    width: int
    height: int
    selected_frames: int
    visual_tokens: int
    accepted: bool
    rejection_reason: RejectionReason | None


def evaluate_inference_budget(
    width: int, height: int, selected_frames: int
) -> InferenceBudget:
    """Evaluate the actual model tensor and selected frames for admission."""

    if width <= 0 or height <= 0 or selected_frames <= 0:
        raise ValueError("width, height, and selected_frames must all be positive")

    patch_columns = (width + PATCH_SIZE - 1) // PATCH_SIZE
    patch_rows = (height + PATCH_SIZE - 1) // PATCH_SIZE
    temporal_groups = (selected_frames + TEMPORAL_STRIDE - 1) // TEMPORAL_STRIDE
    visual_tokens = temporal_groups * patch_columns * patch_rows

    if visual_tokens < MIN_VISUAL_TOKENS:
        rejection_reason: RejectionReason | None = "below_minimum"
    elif visual_tokens > MAX_VISUAL_TOKENS:
        rejection_reason = "above_maximum"
    else:
        rejection_reason = None

    return InferenceBudget(
        width=width,
        height=height,
        selected_frames=selected_frames,
        visual_tokens=visual_tokens,
        accepted=rejection_reason is None,
        rejection_reason=rejection_reason,
    )
