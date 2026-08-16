"""Canonical source, time-range, and evidence-window contracts."""

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from .._base import (
    DomainModel,
    register_enum,
    register_model,
    require_non_negative_integer,
    require_text,
)


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
        require_non_negative_integer(self.start, "frame start")
        require_non_negative_integer(self.end, "frame end")
        if self.end <= self.start:
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
class SourceClock(DomainModel):
    """Mapping from integer presentation timestamps to a bounded UTC timeline."""

    utc_origin: datetime
    pts_origin: int
    pts_end: int
    time_base_numerator: int
    time_base_denominator: int

    def __post_init__(self) -> None:
        if (
            not isinstance(self.utc_origin, datetime)
            or self.utc_origin.tzinfo is None
            or self.utc_origin.utcoffset() != timezone.utc.utcoffset(self.utc_origin)
        ):
            raise ValueError("utc_origin must be timezone-aware UTC")
        for value, name in (
            (self.pts_origin, "pts_origin"),
            (self.pts_end, "pts_end"),
            (self.time_base_numerator, "time_base_numerator"),
            (self.time_base_denominator, "time_base_denominator"),
        ):
            require_non_negative_integer(value, name)
        if self.pts_end <= self.pts_origin:
            raise ValueError("pts_end must be after pts_origin")
        if self.time_base_numerator == 0 or self.time_base_denominator == 0:
            raise ValueError("time base values must be positive")


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
    checksum: str = "unspecified"
    frame_count: int | None = None
    clock: SourceClock | None = None

    def __post_init__(self) -> None:
        require_text(self.source_id, "source_id")
        require_text(self.media_locator, "media_locator")
        require_text(self.codec, "codec")
        require_text(self.checksum, "checksum")
        require_non_negative_integer(self.width, "source width")
        require_non_negative_integer(self.height, "source height")
        if (
            self.width == 0
            or self.height == 0
            or isinstance(self.nominal_frame_rate, bool)
            or not isinstance(self.nominal_frame_rate, (int, float))
            or self.nominal_frame_rate <= 0
        ):
            raise ValueError("source dimensions and frame rate must be positive")
        if self.frame_count is not None:
            require_non_negative_integer(self.frame_count, "frame_count")
        if self.clock is not None and not isinstance(self.clock, SourceClock):
            raise ValueError("clock must be SourceClock")
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
        require_non_negative_integer(self.expected_frame_count, "expected_frame_count")
        require_non_negative_integer(self.observed_frame_count, "observed_frame_count")
        if not isinstance(self.completeness, Completeness):
            object.__setattr__(self, "completeness", Completeness(self.completeness))


        if self.completeness is Completeness.COMPLETE and (
            self.expected_frame_count == 0
            or self.observed_frame_count != self.expected_frame_count
        ):
            raise ValueError("complete windows require every expected frame")
        if self.completeness is Completeness.PARTIAL and self.observed_frame_count == 0:
            raise ValueError("partial windows require observed frames")
        if self.completeness is Completeness.GAP and self.observed_frame_count != 0:
            raise ValueError("gap windows cannot contain observed frames")


__all__ = [
    "Completeness",
    "EvidenceWindow",
    "FrameRange",
    "RetentionClass",
    "Source",
    "SourceClock",
    "SourceReference",
    "TimeRange",
]
