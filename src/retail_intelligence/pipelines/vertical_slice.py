"""Deterministic orchestration for the first cited-answer vertical slice."""

from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Protocol

from ..domain.identity import PipelineIdentity
from ..domain.intelligence import (
    EvidenceLink, IntelligenceContext, Observation, ObservationKind, PersistenceState,
    PipelineProvenance, PipelineRun, PipelineRunState,
)
from ..domain.media import Source
from ..domain.query import Abstention, Answer, AnswerState, Citation
from .file_ingest import FileWindowFormer


class CaptionModel(Protocol):
    def caption(self, source: Source, window_id: str) -> str: ...


class AnswerModel(Protocol):
    def answer(self, question: str, observations: tuple[Observation, ...]) -> str | None: ...


class EvidenceIndex(Protocol):
    def upsert(self, observation: Observation) -> None: ...
    def search(self, source: Source, question: str) -> tuple[Observation, ...]: ...
    def state(self, window_id: str) -> PersistenceState: ...
    def count(self) -> int: ...


@dataclass(frozen=True, slots=True)
class SliceStatus:
    pipeline_run: PipelineRun
    index_state: PersistenceState
    evidence_count: int
    index_count: int


class VerticalSlice:
    """Runs registration, evidence creation, indexing, and cited Q&A."""

    PIPELINE_VERSION = "vertical-slice-v1"
    CONFIGURATION = {"caption_prompt": "observable activity", "window_seconds": 10}

    def __init__(self, storage, index: EvidenceIndex,
                 caption_model: CaptionModel, answer_model: AnswerModel) -> None:
        self._storage = storage
        self._index = index
        self._caption_model = caption_model
        self._answer_model = answer_model

    def process(self, source: Source, timestamps: tuple[int | None, ...]) -> SliceStatus:
        path = Path(source.media_locator)
        if not path.is_file():
            raise ValueError("source media_locator must name a local file")
        if source.checksum != self._checksum(path):
            raise ValueError("source checksum does not match the local file")
        former = FileWindowFormer(self._storage)
        former.register(source)
        formation = former.form_windows(
            source, timestamps, 10, self.PIPELINE_VERSION, self.CONFIGURATION
        )
        if len(formation.windows) != 1:
            raise ValueError("the vertical slice requires exactly one evidence window")
        window = formation.windows[0]
        identity = PipelineIdentity(
            source.checksum, window.time_range, self.PIPELINE_VERSION, self.CONFIGURATION
        )
        run = PipelineRun(
            identity.pipeline_run_id, source.reference, window.time_range,
            self.PIPELINE_VERSION, identity.configuration_id, PipelineRunState.QUEUED,
        )
        existing = self._storage.get_pipeline_run(run.pipeline_run_id)
        if existing is not None and existing.state is PipelineRunState.SUCCEEDED:
            return self.status(existing)
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

    def _observation(self, source, window, identity):
        link = EvidenceLink(source.reference, window.window_id, window.time_range,
                            window.frame_range, source.media_locator)
        provenance = PipelineProvenance(
            "caption-model", "fixture-v1", identity.configuration_id,
            tuple((key, str(value)) for key, value in sorted(self.CONFIGURATION.items())),
            identity.pipeline_run_id,
        )
        context = IntelligenceContext(
            source.reference, provenance, (link,), 1.0, window.time_range.end,
            source.retention_class,
        )
        return Observation(
            identity.observation_id(ObservationKind.CAPTION.value, 0),
            ObservationKind.CAPTION, self._caption_model.caption(source, window.window_id),
            context, "fixture://caption/one",
        )

    @staticmethod
    def _checksum(path: Path) -> str:
        return "sha256:" + sha256(path.read_bytes()).hexdigest()


__all__ = ["AnswerModel", "CaptionModel", "EvidenceIndex", "SliceStatus", "VerticalSlice"]
