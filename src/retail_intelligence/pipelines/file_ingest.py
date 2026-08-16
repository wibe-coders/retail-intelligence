"""Register file metadata and form evidence windows from presentation timestamps."""

from dataclasses import dataclass
from datetime import timedelta
from enum import Enum
from math import ceil, floor, isfinite
from typing import Any, Mapping

from ..domain.identity import PipelineIdentity
from ..domain.media import Completeness, EvidenceWindow, FrameRange, Source, TimeRange
from ..ports.storage import SourceStorage


class TimestampIssue(str, Enum):
    MISSING = "missing"
    DUPLICATE = "duplicate"
    OUT_OF_ORDER = "out_of_order"


@dataclass(frozen=True, slots=True)
class FrameTimestamp:
    frame_index: int
    presentation_timestamp: int | None
    issues: tuple[TimestampIssue, ...] = ()
    window_id: str | None = None


@dataclass(frozen=True, slots=True)
class WindowFormation:
    windows: tuple[EvidenceWindow, ...]
    frame_timestamps: tuple[FrameTimestamp, ...]


class FileWindowFormer:
    """Pure timestamp windowing with registration delegated to a storage port."""

    def __init__(self, source_storage: SourceStorage) -> None:
        self._source_storage = source_storage

    def register(self, source: Source) -> Source:
        if source.clock is None or source.frame_count is None:
            raise ValueError("file sources require clock metadata and frame_count")
        if source.checksum == "unspecified":
            raise ValueError("file sources require a content checksum")
        return self._source_storage.save_source(source)

    def form_windows(
        self,
        source: Source,
        timestamps: tuple[int | None, ...],
        window_seconds: float,
        pipeline_version: str,
        configuration: Mapping[str, Any] | str,
    ) -> WindowFormation:
        if source.clock is None or source.frame_count is None:
            raise ValueError("file sources require clock metadata and frame_count")
        if source.checksum == "unspecified":
            raise ValueError("file sources require a content checksum")
        if len(timestamps) != source.frame_count:
            raise ValueError("timestamp count must match source frame_count")
        if (
            isinstance(window_seconds, bool)
            or not isinstance(window_seconds, (int, float))
            or not isfinite(window_seconds)
            or window_seconds <= 0
        ):
            raise ValueError("window_seconds must be positive")

        ranges = self._ranges(source, window_seconds)
        assignments, frame_windows, records = self._assign(
            source, timestamps, ranges, window_seconds
        )
        windows = tuple(
            self._window(
                source,
                interval,
                assignments[index],
                window_seconds,
                pipeline_version,
                configuration,
            )
            for index, interval in enumerate(ranges)
        )
        window_ids = {index: window.window_id for index, window in enumerate(windows)}
        records = tuple(
            FrameTimestamp(
                record.frame_index,
                record.presentation_timestamp,
                record.issues,
                window_ids.get(frame_windows.get(record.frame_index)),
            )
            for record in records
        )
        return WindowFormation(windows, records)

    @staticmethod
    def _ranges(source: Source, window_seconds: float) -> tuple[TimeRange, ...]:
        clock = source.clock
        assert clock is not None
        duration = (
            (clock.pts_end - clock.pts_origin)
            * clock.time_base_numerator
            / clock.time_base_denominator
        )
        count = ceil(duration / window_seconds)
        return tuple(
            TimeRange(
                clock.utc_origin + timedelta(seconds=index * window_seconds),
                clock.utc_origin
                + timedelta(seconds=min((index + 1) * window_seconds, duration)),
            )
            for index in range(count)
        )

    @staticmethod
    def _assign(source, timestamps, ranges, window_seconds):
        clock = source.clock
        assignments = {index: [] for index in range(len(ranges))}
        frame_windows = {}
        records = []
        seen = set()
        previous = None
        for frame_index, pts in enumerate(timestamps):
            issues = []
            if pts is None:
                issues.append(TimestampIssue.MISSING)
            else:
                if isinstance(pts, bool) or not isinstance(pts, int):
                    raise ValueError("presentation timestamps must be integers or None")
                if pts in seen:
                    issues.append(TimestampIssue.DUPLICATE)
                if previous is not None and pts < previous:
                    issues.append(TimestampIssue.OUT_OF_ORDER)
                seen.add(pts)
                previous = pts
                seconds = (
                    (pts - clock.pts_origin)
                    * clock.time_base_numerator
                    / clock.time_base_denominator
                )
                if 0 <= seconds < (ranges[-1].end - clock.utc_origin).total_seconds():
                    window_index = min(floor(seconds / window_seconds), len(ranges) - 1)
                    assignments[window_index].append(frame_index)
                    frame_windows[frame_index] = window_index
            records.append(FrameTimestamp(frame_index, pts, tuple(issues)))
        return assignments, frame_windows, records

    @staticmethod
    def _window(
        source, interval, frame_assignments, window_seconds, pipeline_version, configuration
    ):
        indices = tuple(frame_assignments)
        observed = len(indices)
        duration = (interval.end - interval.start).total_seconds()
        expected = ceil(source.nominal_frame_rate * duration)
        if observed == 0:
            completeness = Completeness.GAP
        elif duration < window_seconds or observed != expected:
            completeness = Completeness.PARTIAL
        else:
            completeness = Completeness.COMPLETE
        identity = PipelineIdentity(source.checksum, interval, pipeline_version, configuration)
        frame_range = FrameRange(min(indices), max(indices) + 1) if indices else None
        return EvidenceWindow(
            identity.evidence_window_id,
            source.reference,
            interval,
            frame_range,
            expected,
            observed,
            pipeline_version,
            identity.configuration_id,
            completeness,
        )
