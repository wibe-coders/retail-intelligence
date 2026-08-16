"""Store-authorized query and evidence-clip application boundary."""

from dataclasses import dataclass
from pathlib import Path

from ..domain.query import Answer
from ..pipelines.vertical_slice import VerticalSlice


class AuthorizationError(PermissionError):
    pass


@dataclass(frozen=True, slots=True)
class AuthorizationContext:
    subject: str
    store_ids: frozenset[str]


@dataclass(frozen=True, slots=True)
class AuthorizedClip:
    content: bytes
    content_type: str
    camera_id: str
    utc_start: str
    utc_end: str


class PublicApi:
    """The only caller-facing route to answers and source media."""

    def __init__(self, storage, vertical_slice: VerticalSlice) -> None:
        self._storage = storage
        self._vertical_slice = vertical_slice

    def ask(self, auth: AuthorizationContext, source_id: str, question: str) -> Answer:
        source = self._storage.get_source(source_id)
        if source is None:
            raise LookupError("source not found")
        self._authorize(auth, source.reference.store_id)
        return self._vertical_slice.ask(source, question)

    def get_citation_clip(
        self, auth: AuthorizationContext, citation_id: str
    ) -> AuthorizedClip:
        citation = self._storage.get_citation(citation_id)
        if citation is None:
            raise LookupError("citation not found")
        evidence = citation.evidence
        self._authorize(auth, evidence.source.store_id)
        window = self._storage.get_evidence_window(evidence.evidence_window_id)
        if window is None or window.source != evidence.source:
            raise LookupError("cited evidence is unavailable")
        sources = self._storage.find_sources(
            evidence.source.store_id,
            evidence.source.camera_id,
            evidence.source.recording_id,
        )
        if len(sources) != 1 or sources[0].media_locator != evidence.media_locator:
            raise LookupError("cited source is unavailable")
        path = Path(sources[0].media_locator)
        if not path.is_file():
            raise LookupError("cited media is unavailable")
        return AuthorizedClip(
            path.read_bytes(), "video/mp4", evidence.source.camera_id,
            evidence.time_range.start.isoformat(), evidence.time_range.end.isoformat(),
        )

    @staticmethod
    def _authorize(auth: AuthorizationContext, store_id: str) -> None:
        if not auth.subject or store_id not in auth.store_ids:
            raise AuthorizationError("subject is not authorized for this store")


__all__ = ["AuthorizationContext", "AuthorizationError", "AuthorizedClip", "PublicApi"]
