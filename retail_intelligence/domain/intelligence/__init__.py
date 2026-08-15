"""Canonical observations, derived intelligence, and provenance contracts."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .._base import DomainModel, register_enum, register_model, require_text, validate_confidence
from ..media import Completeness, FrameRange, RetentionClass, SourceReference, TimeRange


@register_enum
class ObservationKind(str, Enum):
    BOX = "box"
    TRACK = "track"
    CAPTION = "caption"


@register_model
@dataclass(frozen=True, slots=True)
class PipelineProvenance(DomainModel):
    model: str
    model_version: str
    configuration_id: str
    configuration: tuple[tuple[str, str], ...]
    pipeline_run_id: str

    def __post_init__(self) -> None:
        for value, name in ((self.model, "model"), (self.model_version, "model_version"),
                            (self.configuration_id, "configuration_id"),
                            (self.pipeline_run_id, "pipeline_run_id")):
            require_text(value, name)
        if any(not key.strip() or not value.strip() for key, value in self.configuration):
            raise ValueError("configuration keys and values cannot be blank")


@register_model
@dataclass(frozen=True, slots=True)
class EvidenceLink(DomainModel):
    source: SourceReference
    evidence_window_id: str
    time_range: TimeRange
    frame_range: FrameRange | None
    media_locator: str

    def __post_init__(self) -> None:
        require_text(self.evidence_window_id, "evidence_window_id")
        require_text(self.media_locator, "media_locator")


@register_model
@dataclass(frozen=True, slots=True)
class IntelligenceContext(DomainModel):
    """Required source, pipeline, lifecycle, and evidence metadata."""

    source: SourceReference
    provenance: PipelineProvenance
    evidence: tuple[EvidenceLink, ...]
    confidence: float | None
    created_at: datetime
    retention_class: RetentionClass

    def __post_init__(self) -> None:
        if not self.evidence:
            raise ValueError("at least one evidence link is required")
        validate_confidence(self.confidence)
        if self.created_at.tzinfo is None or self.created_at.utcoffset() != timezone.utc.utcoffset(self.created_at):
            raise ValueError("created_at must be timezone-aware UTC")
        if any(link.source != self.source for link in self.evidence):
            raise ValueError("evidence source must match intelligence source")
        if not isinstance(self.retention_class, RetentionClass):
            object.__setattr__(self, "retention_class", RetentionClass(self.retention_class))


@register_model
@dataclass(frozen=True, slots=True)
class Observation(DomainModel):
    observation_id: str
    kind: ObservationKind
    value: str
    context: IntelligenceContext
    vendor_output_reference: str

    def __post_init__(self) -> None:
        require_text(self.observation_id, "observation_id")
        require_text(self.value, "value")
        require_text(self.vendor_output_reference, "vendor_output_reference")
        if not isinstance(self.kind, ObservationKind):
            object.__setattr__(self, "kind", ObservationKind(self.kind))


@register_model
@dataclass(frozen=True, slots=True)
class Event(DomainModel):
    event_id: str
    event_type: str
    observation_ids: tuple[str, ...]
    derivation: PipelineProvenance
    context: IntelligenceContext

    def __post_init__(self) -> None:
        require_text(self.event_id, "event_id")
        require_text(self.event_type, "event_type")
        if not self.observation_ids or any(not value.strip() for value in self.observation_ids):
            raise ValueError("events require input observation identifiers")


@register_model
@dataclass(frozen=True, slots=True)
class Metric(DomainModel):
    metric_id: str
    name: str
    value: float
    event_ids: tuple[str, ...]
    filters: tuple[tuple[str, str], ...]
    interval: TimeRange
    context: IntelligenceContext

    def __post_init__(self) -> None:
        require_text(self.metric_id, "metric_id")
        require_text(self.name, "name")
        if not self.event_ids:
            raise ValueError("metrics require input event identifiers")


@register_model
@dataclass(frozen=True, slots=True)
class Insight(DomainModel):
    insight_id: str
    text: str
    supporting_object_ids: tuple[str, ...]
    context: IntelligenceContext

    def __post_init__(self) -> None:
        require_text(self.insight_id, "insight_id")
        require_text(self.text, "text")
        if not self.supporting_object_ids:
            raise ValueError("insights require a supporting evidence chain")


__all__ = [
    "Event", "EvidenceLink", "Insight", "IntelligenceContext", "Metric", "Observation",
    "ObservationKind", "PipelineProvenance",
]
