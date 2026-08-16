"""Deterministic orchestration for the first cited-answer vertical slice."""

from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping, Protocol

from ..domain.identity import PipelineIdentity
from ..domain.intelligence import (
    EvidenceLink, IntelligenceContext, Observation, ObservationKind, PersistenceState,
    PipelineProvenance, PipelineRun, PipelineRunState,
)
from ..domain.media import Source
from ..domain.query import Abstention, Answer, AnswerState, Citation
from ..ports.storage import (
    CitationStorage, EvidenceWindowStorage, IntelligenceStorage, PipelineRunStorage,
    SourceStorage,
)
from .file_ingest import FileWindowFormer


class CaptionModel(Protocol):
    def caption(self, source: Source, window_id: str) -> "CaptionModelResult": ...


class AnswerModel(Protocol):
    def answer(self, question: str, observations: tuple[Observation, ...]) -> str | None: ...


class EvidenceIndex(Protocol):
    def upsert(self, observation: Observation) -> None: ...
    def search(self, source: Source, question: str) -> tuple[Observation, ...]: ...
    def state(self, window_id: str) -> PersistenceState: ...
    def count(self) -> int: ...


class VerticalSliceStorage(
    SourceStorage, EvidenceWindowStorage, IntelligenceStorage, PipelineRunStorage,
    CitationStorage, Protocol,
):
    pass


@dataclass(frozen=True, slots=True)
class SliceStatus:
    pipeline_run: PipelineRun
    index_state: PersistenceState
    evidence_count: int
    index_count: int


@dataclass(frozen=True, slots=True)
class CaptionModelResult:
    text: str
    model: str
    model_version: str
    vendor_output_reference: str

    def __post_init__(self) -> None:
        for value, name in (
            (self.text, "text"),
            (self.model, "model"),
            (self.model_version, "model_version"),
            (self.vendor_output_reference, "vendor_output_reference"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} is required")


class VerticalSlice:
    """Runs registration, evidence creation, indexing, and cited Q&A."""

    PIPELINE_VERSION = "vertical-slice-v1"
    CONFIGURATION = {"caption_prompt": "observable activity", "window_seconds": 10}

    def __init__(
        self,
        storage: VerticalSliceStorage,
        index: EvidenceIndex,
        caption_model: CaptionModel,
        answer_model: AnswerModel,
        *,
        pipeline_version: str = PIPELINE_VERSION,
        configuration: Mapping[str, Any] | None = None,
    ) -> None:
        self._storage = storage
        self._index = index
        self._caption_model = caption_model
        self._answer_model = answer_model
        self._pipeline_version = pipeline_version
        self._configuration = dict(
            self.CONFIGURATION if configuration is None else configuration
        )

    def process(self, source: Source, timestamps: tuple[int | None, ...]) -> SliceStatus:
        path = Path(source.media_locator)
        if not path.is_file():
            raise ValueError("source media_locator must name a local file")
        if source.checksum != self._checksum(path):
            raise ValueError("source checksum does not match the local file")
        former = FileWindowFormer(self._storage)
        former.register(source)
        formation = former.form_windows(
            source,
            timestamps,
            self._configuration.get("window_seconds"),
            self._pipeline_version,
            self._configuration,
        )
        if len(formation.windows) != 1:
            raise ValueError("the vertical slice requires exactly one evidence window")
        window = formation.windows[0]
        identity = PipelineIdentity(
            source.checksum,
            window.time_range,
            self._pipeline_version,
            self._configuration,
        )
        run = PipelineRun(
            identity.pipeline_run_id, source.reference, window.time_range,
            self._pipeline_version, identity.configuration_id, PipelineRunState.QUEUED,
        )
        existing = self._storage.get_pipeline_run(run.pipeline_run_id)
        if existing is not None and existing.state is PipelineRunState.SUCCEEDED:
            return self._recover_index(existing)
        self._storage.save_pipeline_run(run)
        self._storage.save_pipeline_run(replace(run, state=PipelineRunState.RUNNING))
        self._storage.save_evidence_window(window)
        observation = self._observation(source, window, identity)
        self._storage.save_observation(observation)
        self._index.upsert(observation)
        succeeded = replace(run, state=PipelineRunState.SUCCEEDED)
        self._storage.save_pipeline_run(succeeded)
        return self.status(succeeded)

    def ask(self, source: Source, question: str) -> Answer:
        observations = self._index.search(source, question)
        text = self._answer_model.answer(question, observations)
        digest = sha256(f"{source.source_id}\0{question}".encode()).hexdigest()[:24]
        answer_id = "answer_" + digest
        if text is None or not observations:
            return Answer(
                answer_id, AnswerState.UNSUPPORTED, None, None, (),
                Abstention(AnswerState.UNSUPPORTED, "No indexed evidence supports this question."),
            )
        citation = Citation("citation_" + digest, observations[0].context.evidence[0], text)
        self._storage.save_citation(citation)
        return Answer(answer_id, AnswerState.SUPPORTED, text, 1.0, (citation,), None)

    def status(self, run: PipelineRun) -> SliceStatus:
        windows = self._storage.find_evidence_windows(run.source, run.time_range)
        state = self._index.state(windows[0].window_id) if windows else PersistenceState.PENDING
        return SliceStatus(run, state, len(windows), self._index.count())

    def _recover_index(self, run: PipelineRun) -> SliceStatus:
        windows = self._storage.find_evidence_windows(run.source, run.time_range)
        if len(windows) != 1:
            raise RuntimeError("succeeded run must have exactly one durable evidence window")
        observations = self._storage.find_observations(run.source, run.time_range)
        if not observations:
            raise RuntimeError("succeeded run must have durable observations")
        for observation in observations:
            self._index.upsert(observation)
        return self.status(run)

    def _observation(self, source, window, identity):
        caption = self._caption_model.caption(source, window.window_id)
        link = EvidenceLink(source.reference, window.window_id, window.time_range,
                            window.frame_range, source.media_locator)
        provenance = PipelineProvenance(
            caption.model, caption.model_version, identity.configuration_id,
            tuple((key, str(value)) for key, value in sorted(self._configuration.items())),
            identity.pipeline_run_id,
        )
        context = IntelligenceContext(
            source.reference, provenance, (link,), 1.0, window.time_range.end,
            source.retention_class,
        )
        return Observation(
            identity.observation_id(ObservationKind.CAPTION.value, 0),
            ObservationKind.CAPTION, caption.text, context, caption.vendor_output_reference,
        )

    @staticmethod
    def _checksum(path: Path) -> str:
        return "sha256:" + sha256(path.read_bytes()).hexdigest()


__all__ = [
    "AnswerModel", "CaptionModel", "CaptionModelResult", "EvidenceIndex", "SliceStatus",
    "VerticalSlice", "VerticalSliceStorage",
]
