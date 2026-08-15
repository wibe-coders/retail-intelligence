"""Canonical cited-answer and abstention contracts."""

from dataclasses import dataclass
from enum import Enum

from .._base import DomainModel, register_enum, register_model, require_text, validate_confidence
from ..intelligence import EvidenceLink


@register_enum
class AnswerState(str, Enum):
    SUPPORTED = "supported"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"
    OUT_OF_RETENTION = "out_of_retention"


@register_model
@dataclass(frozen=True, slots=True)
class Citation(DomainModel):
    citation_id: str
    evidence: EvidenceLink
    claim: str

    def __post_init__(self) -> None:
        require_text(self.citation_id, "citation_id")
        require_text(self.claim, "claim")


@register_model
@dataclass(frozen=True, slots=True)
class Abstention(DomainModel):
    state: AnswerState
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.state, AnswerState):
            object.__setattr__(self, "state", AnswerState(self.state))
        if self.state is AnswerState.SUPPORTED:
            raise ValueError("a supported answer cannot contain an abstention")
        require_text(self.reason, "reason")


@register_model
@dataclass(frozen=True, slots=True)
class Answer(DomainModel):
    answer_id: str
    state: AnswerState
    text: str | None
    confidence: float | None
    citations: tuple[Citation, ...]
    abstention: Abstention | None

    def __post_init__(self) -> None:
        require_text(self.answer_id, "answer_id")
        if not isinstance(self.state, AnswerState):
            object.__setattr__(self, "state", AnswerState(self.state))
        validate_confidence(self.confidence)
        if self.state is AnswerState.SUPPORTED:
            if not self.text or not self.text.strip() or not self.citations:
                raise ValueError("supported answers require text and citations")
            if self.abstention is not None:
                raise ValueError("supported answers cannot abstain")
        elif self.abstention is None or self.abstention.state is not self.state:
            raise ValueError("non-supported answers require a matching abstention")


__all__ = ["Abstention", "Answer", "AnswerState", "Citation"]
