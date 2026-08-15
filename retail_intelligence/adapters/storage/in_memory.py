"""Deterministic process-local evidence storage for tests and experiments."""

from collections.abc import Callable
from typing import TypeVar

from ...domain.intelligence import Event, Observation, PipelineRun
from ...domain.media import EvidenceWindow, Source, SourceReference, TimeRange
from ...domain.query import Citation


class ConflictingRecordError(ValueError):
    """An immutable identifier was reused with different content."""


Record = TypeVar("Record")


class InMemoryEvidenceStorage:
    """Implements all evidence ports without a database or framework dependency."""

    def __init__(self) -> None:
        self._sources: dict[str, Source] = {}
        self._windows: dict[str, EvidenceWindow] = {}
        self._observations: dict[str, Observation] = {}
        self._events: dict[str, Event] = {}
        self._pipeline_runs: dict[str, PipelineRun] = {}
        self._citations: dict[str, Citation] = {}

    def save_source(self, source: Source) -> Source:
        return self._save(self._sources, source.source_id, source)

    def get_source(self, source_id: str) -> Source | None:
        return self._sources.get(source_id)

    def find_sources(
        self, store_id: str, camera_id: str | None = None, recording_id: str | None = None
    ) -> tuple[Source, ...]:
        return self._sorted(
            (
                source
                for source in self._sources.values()
                if source.reference.store_id == store_id
                and (camera_id is None or source.reference.camera_id == camera_id)
                and (recording_id is None or source.reference.recording_id == recording_id)
            ),
            lambda source: source.source_id,
        )

    def save_evidence_window(self, window: EvidenceWindow) -> EvidenceWindow:
        return self._save(self._windows, window.window_id, window)

    def get_evidence_window(self, window_id: str) -> EvidenceWindow | None:
        return self._windows.get(window_id)

    def find_evidence_windows(
        self, source: SourceReference, time_range: TimeRange
    ) -> tuple[EvidenceWindow, ...]:
        return self._find_temporal(
            self._windows.values(), source, time_range,
            lambda window: window.source, lambda window: window.time_range,
            lambda window: window.window_id,
        )

    def save_observation(self, observation: Observation) -> Observation:
        return self._save(self._observations, observation.observation_id, observation)

    def save_event(self, event: Event) -> Event:
        return self._save(self._events, event.event_id, event)

    def find_observations(
        self, source: SourceReference, time_range: TimeRange
    ) -> tuple[Observation, ...]:
        return self._find_intelligence(
            self._observations.values(), source, time_range,
            lambda item: item.observation_id,
        )

    def find_events(
        self, source: SourceReference, time_range: TimeRange
    ) -> tuple[Event, ...]:
        return self._find_intelligence(
            self._events.values(), source, time_range, lambda item: item.event_id
        )

    def save_pipeline_run(self, run: PipelineRun) -> PipelineRun:
        return self._save(self._pipeline_runs, run.pipeline_run_id, run)

    def get_pipeline_run(self, pipeline_run_id: str) -> PipelineRun | None:
        return self._pipeline_runs.get(pipeline_run_id)

    def find_pipeline_runs(
        self, source: SourceReference, time_range: TimeRange
    ) -> tuple[PipelineRun, ...]:
        return self._find_temporal(
            self._pipeline_runs.values(), source, time_range,
            lambda run: run.source, lambda run: run.time_range,
            lambda run: run.pipeline_run_id,
        )

    def save_citation(self, citation: Citation) -> Citation:
        return self._save(self._citations, citation.citation_id, citation)

    def get_citation(self, citation_id: str) -> Citation | None:
        return self._citations.get(citation_id)

    def find_citations(
        self, source: SourceReference, time_range: TimeRange
    ) -> tuple[Citation, ...]:
        return self._find_temporal(
            self._citations.values(), source, time_range,
            lambda citation: citation.evidence.source,
            lambda citation: citation.evidence.time_range,
            lambda citation: citation.citation_id,
        )

    @staticmethod
    def _save(records: dict[str, Record], identifier: str, record: Record) -> Record:
        existing = records.get(identifier)
        if existing is not None and existing != record:
            raise ConflictingRecordError(
                f"identifier {identifier!r} already has different immutable content"
            )
        records[identifier] = record
        return record

    @classmethod
    def _find_intelligence(cls, records, source, time_range, identifier):
        return cls._sorted(
            (record for record in records if record.context.source == source and any(
                cls._overlaps(link.time_range, time_range) for link in record.context.evidence
            )),
            identifier,
        )

    @classmethod
    def _find_temporal(cls, records, source, time_range, record_source, interval, identifier):
        return cls._sorted(
            (record for record in records
             if record_source(record) == source and cls._overlaps(interval(record), time_range)),
            identifier,
        )

    @staticmethod
    def _overlaps(left: TimeRange, right: TimeRange) -> bool:
        return left.start < right.end and right.start < left.end

    @staticmethod
    def _sorted(records, identifier: Callable[[Record], str]) -> tuple[Record, ...]:
        return tuple(sorted(records, key=identifier))
