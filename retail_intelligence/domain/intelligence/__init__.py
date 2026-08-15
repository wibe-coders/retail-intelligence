"""Canonical observations, derived intelligence, and provenance contracts."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .._base import (
    DomainModel,
    register_enum,
    register_model,
    require_text,
    require_text_tuple,
    validate_confidence,
)
from ..media import (
    Completeness,
    EvidenceWindow,
    FrameRange,
    RetentionClass,
    SourceReference,
    TimeRange,
)


@register_enum
class ObservationKind(str, Enum):
    BOX = "box"
    TRACK = "track"
    CAPTION = "caption"


@register_enum
class PersistenceState(str, Enum):
    PENDING = "pending"
    STORED = "stored"
    INDEXED = "indexed"
    FAILED = "failed"


@register_model
@dataclass(frozen=True, slots=True)
class PipelineProvenance(DomainModel):
    model: str
    model_version: str
    configuration_id: str
    configuration: tuple[tuple[str, str], ...]
    pipeline_run_id: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.model, "model"),
            (self.model_version, "model_version"),
            (self.configuration_id, "configuration_id"),
            (self.pipeline_run_id, "pipeline_run_id"),
        ):
            require_text(value, name)
        if not isinstance(self.configuration, tuple):
            raise ValueError("configuration must be an immutable tuple")
        for item in self.configuration:
            if not isinstance(item, tuple) or len(item) != 2:
                raise ValueError("configuration entries must be key-value tuples")
            require_text(item[0], "configuration key")
            require_text(item[1], "configuration value")


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
        if (
            not isinstance(self.created_at, datetime)
            or self.created_at.tzinfo is None
            or self.created_at.utcoffset() != timezone.utc.utcoffset(self.created_at)
        ):
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
        require_text_tuple(self.observation_ids, "observation_ids")


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
        require_text_tuple(self.event_ids, "event_ids")
        if not isinstance(self.filters, tuple):
            raise ValueError("filters must be an immutable tuple")


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
        require_text_tuple(self.supporting_object_ids, "supporting_object_ids")


@register_model
@dataclass(frozen=True, slots=True)
class EvidenceRecord(DomainModel):
    """Durable normalized contents and persistence state for one window."""

    window: EvidenceWindow
    observations: tuple[Observation, ...]
    events: tuple[Event, ...]
    missing_stages: tuple[str, ...]
    storage_state: PersistenceState
    index_state: PersistenceState
    last_error: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.observations, tuple) or not isinstance(self.events, tuple):
            raise ValueError("observations and events must be immutable tuples")
        if not isinstance(self.missing_stages, tuple):
            raise ValueError("missing_stages must be an immutable tuple")
        if self.window.completeness is Completeness.COMPLETE and self.missing_stages:
            raise ValueError("complete evidence cannot have missing stages")
        intelligence_objects = (*self.observations, *self.events)
        for intelligence_object in intelligence_objects:
            context = intelligence_object.context
            if context.source != self.window.source:
                raise ValueError("record contents must use the evidence window source")
            if not any(
                link.evidence_window_id == self.window.window_id
                for link in context.evidence
            ):
                raise ValueError("record contents must link to the evidence window")
        if not isinstance(self.storage_state, PersistenceState):
            object.__setattr__(self, "storage_state", PersistenceState(self.storage_state))
        if not isinstance(self.index_state, PersistenceState):
            object.__setattr__(self, "index_state", PersistenceState(self.index_state))
        if self.last_error is not None:
            require_text(self.last_error, "last_error")


__all__ = [
    "Event",
    "EvidenceLink",
    "EvidenceRecord",
    "Insight",
    "IntelligenceContext",
    "Metric",
    "Observation",
    "ObservationKind",
    "PersistenceState",
    "PipelineProvenance",
]
