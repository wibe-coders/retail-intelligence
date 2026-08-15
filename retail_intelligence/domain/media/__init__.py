"""Canonical source, time-range, and evidence-window contracts."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .._base import DomainModel, register_enum, register_model, require_text


@register_enum
class RetentionClass(str, Enum):
    TRANSIENT = "transient"
    STANDARD = "standard"
    ARCHIVE = "archive"


@register_enum
class Completeness(str, Enum):
    COMPLETE = "complete"
    PARTIAL = "partial"
    GAP = "gap"


@register_model
@dataclass(frozen=True, slots=True)
class TimeRange(DomainModel):
    """A non-empty, half-open UTC interval: ``[start, end)``."""

    start: datetime
    end: datetime

    def __post_init__(self) -> None:
        for value, name in ((self.start, "start"), (self.end, "end")):
            if not isinstance(value, datetime) or value.tzinfo is None:
                raise ValueError(f"{name} must be timezone-aware UTC")
            if value.utcoffset() != timezone.utc.utcoffset(value):
                raise ValueError(f"{name} must be UTC")
        if self.end <= self.start:
            raise ValueError("end must be after start")


@register_model
@dataclass(frozen=True, slots=True)
class FrameRange(DomainModel):
    """A non-empty, half-open source-frame interval."""

    start: int
    end: int

    def __post_init__(self) -> None:
        if isinstance(self.start, bool) or self.start < 0:
            raise ValueError("frame start must be a non-negative integer")
        if isinstance(self.end, bool) or self.end <= self.start:
            raise ValueError("frame end must be after frame start")


@register_model
@dataclass(frozen=True, slots=True)
class SourceReference(DomainModel):
    """Stable identifiers shared by every stored intelligence object."""

    store_id: str
    camera_id: str
    recording_id: str

    def __post_init__(self) -> None:
        require_text(self.store_id, "store_id")
        require_text(self.camera_id, "camera_id")
        require_text(self.recording_id, "recording_id")


@register_model
@dataclass(frozen=True, slots=True)
class Source(DomainModel):
    source_id: str
    reference: SourceReference
    media_locator: str
    codec: str
    width: int
    height: int
    nominal_frame_rate: float
    retention_class: RetentionClass

    def __post_init__(self) -> None:
        require_text(self.source_id, "source_id")
        require_text(self.media_locator, "media_locator")
        require_text(self.codec, "codec")
        if self.width <= 0 or self.height <= 0 or self.nominal_frame_rate <= 0:
            raise ValueError("source dimensions and frame rate must be positive")
        if not isinstance(self.retention_class, RetentionClass):
            object.__setattr__(self, "retention_class", RetentionClass(self.retention_class))


@register_model
@dataclass(frozen=True, slots=True)
class EvidenceWindow(DomainModel):
    window_id: str
    source: SourceReference
    time_range: TimeRange
    frame_range: FrameRange | None
    expected_frame_count: int
    observed_frame_count: int
    pipeline_version: str
    configuration_id: str
    completeness: Completeness

    def __post_init__(self) -> None:
        require_text(self.window_id, "window_id")
        require_text(self.pipeline_version, "pipeline_version")
        require_text(self.configuration_id, "configuration_id")
        if self.expected_frame_count < 0 or self.observed_frame_count < 0:
            raise ValueError("frame counts cannot be negative")
        if self.observed_frame_count > self.expected_frame_count:
            raise ValueError("observed frames cannot exceed expected frames")
        if not isinstance(self.completeness, Completeness):
            object.__setattr__(self, "completeness", Completeness(self.completeness))


__all__ = [
    "Completeness", "EvidenceWindow", "FrameRange", "RetentionClass", "Source",
    "SourceReference", "TimeRange",
]
