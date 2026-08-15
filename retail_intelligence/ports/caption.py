"""Framework-independent contracts for RT-VLM caption inference."""

from dataclasses import dataclass
from enum import Enum
from typing import Any, Protocol

from ..inference_budget import InferenceBudget


@dataclass(frozen=True, slots=True)
class CaptionRequest:
    frames: tuple[Any, ...]
    width: int
    height: int
    selected_frame_count: int

    def __post_init__(self) -> None:
        if not isinstance(self.frames, tuple):
            raise ValueError("frames must be an immutable tuple")
        values = (self.width, self.height, self.selected_frame_count)
        if any(isinstance(value, bool) or not isinstance(value, int) or value <= 0
               for value in values):
            raise ValueError("width, height, and selected_frame_count must be positive integers")


@dataclass(frozen=True, slots=True)
class PreparedCaptionInput:
    """The realized tensor metadata and opaque adapter payload."""

    payload: Any
    width: int
    height: int
    selected_frame_count: int


class CaptionStageState(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    GAP = "gap"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CaptionStageOutcome:
    state: CaptionStageState
    budget: InferenceBudget | None
    response: Any | None
    reason: str | None


class CaptionPreprocessor(Protocol):
    def prepare(self, frames: tuple[Any, ...], width: int, height: int) -> PreparedCaptionInput: ...


class CaptionClient(Protocol):
    def infer(self, prepared_input: PreparedCaptionInput) -> Any: ...


class CaptionPort(Protocol):
    def caption(self, request: CaptionRequest) -> CaptionStageOutcome: ...


__all__ = ["CaptionClient", "CaptionPort", "CaptionPreprocessor", "CaptionRequest",
           "CaptionStageOutcome", "CaptionStageState", "PreparedCaptionInput"]
