"""Narrow, vendor-independent ports for durable evidence records."""

from typing import Protocol

from ..domain.intelligence import Event, Observation, PipelineRun
from ..domain.media import EvidenceWindow, Source, SourceReference, TimeRange
from ..domain.query import Citation


class SourceStorage(Protocol):
    def save_source(self, source: Source) -> Source: ...

    def get_source(self, source_id: str) -> Source | None: ...

    def find_sources(
        self, store_id: str, camera_id: str | None = None, recording_id: str | None = None
    ) -> tuple[Source, ...]: ...


class EvidenceWindowStorage(Protocol):
    def save_evidence_window(self, window: EvidenceWindow) -> EvidenceWindow: ...

    def get_evidence_window(self, window_id: str) -> EvidenceWindow | None: ...

    def find_evidence_windows(
        self, source: SourceReference, time_range: TimeRange
    ) -> tuple[EvidenceWindow, ...]: ...


class IntelligenceStorage(Protocol):
    def save_observation(self, observation: Observation) -> Observation: ...

    def save_event(self, event: Event) -> Event: ...

    def find_observations(
        self, source: SourceReference, time_range: TimeRange
    ) -> tuple[Observation, ...]: ...

    def find_events(
        self, source: SourceReference, time_range: TimeRange
    ) -> tuple[Event, ...]: ...


class PipelineRunStorage(Protocol):
    def save_pipeline_run(self, run: PipelineRun) -> PipelineRun: ...

    def get_pipeline_run(self, pipeline_run_id: str) -> PipelineRun | None: ...

    def find_pipeline_runs(
        self, source: SourceReference, time_range: TimeRange
    ) -> tuple[PipelineRun, ...]: ...


class CitationStorage(Protocol):
    def save_citation(self, citation: Citation) -> Citation: ...

    def get_citation(self, citation_id: str) -> Citation | None: ...

    def find_citations(
        self, source: SourceReference, time_range: TimeRange
    ) -> tuple[Citation, ...]: ...
