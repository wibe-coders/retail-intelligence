import unittest
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from retail_intelligence.adapters.fakes import EvidenceOnlyAnswerModel, FixedCaptionModel
from retail_intelligence.adapters.storage import InMemoryEvidenceIndex, InMemoryEvidenceStorage
from retail_intelligence.apps import AuthorizationContext, PublicApi
from retail_intelligence.apps.public_api import AuthorizationError
from retail_intelligence.domain.intelligence import PersistenceState, PipelineRunState
from retail_intelligence.domain.media import (
    FrameRange, RetentionClass, Source, SourceClock, SourceReference,
)
from retail_intelligence.domain.query import AnswerState
from retail_intelligence.pipelines import VerticalSlice


class VerticalSliceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.path = Path(__file__).parents[1] / "samples" / "hong-kong-passageway.mp4"
        checksum = "sha256:" + sha256(self.path.read_bytes()).hexdigest()
        self.source = Source(
            "source-one-file",
            SourceReference("store-1", "camera-passageway", "recording-one"),
            str(self.path), "h264", 1920, 1080, 1, RetentionClass.STANDARD,
            checksum, FrameRange(0, 10),
            SourceClock(datetime(2026, 8, 16, 12, tzinfo=timezone.utc), 0, 10, 1, 1),
        )
        self.storage = InMemoryEvidenceStorage()
        self.index = InMemoryEvidenceIndex()
        self.caption_model = FixedCaptionModel(
            "A person is walking through the passageway."
        )
        self.slice = VerticalSlice(
            self.storage, self.index,
            self.caption_model,
            EvidenceOnlyAnswerModel(),
        )
        self.api = PublicApi(self.storage, self.slice)
        self.allowed = AuthorizationContext("operator-1", frozenset({"store-1"}))

    def test_one_file_to_authorized_cited_clip_is_idempotent(self) -> None:
        first = self.slice.process(self.source, tuple(range(10)))
        replay = self.slice.process(self.source, tuple(range(10)))

        self.assertEqual(first.pipeline_run.state, PipelineRunState.SUCCEEDED)
        self.assertEqual(first.index_state, PersistenceState.INDEXED)
        self.assertEqual((first.evidence_count, first.index_count), (1, 1))
        self.assertEqual(replay, first)
        self.assertEqual(self.caption_model.call_count, 1)
        answer = self.api.ask(self.allowed, self.source.source_id, "What person is walking?")
        self.assertEqual(answer.state, AnswerState.SUPPORTED)
        citation = answer.citations[0]
        self.assertEqual(citation.evidence.source.camera_id, "camera-passageway")
        self.assertEqual(citation.evidence.time_range.start.tzinfo, timezone.utc)
        clip = self.api.get_citation_clip(self.allowed, citation.citation_id)
        self.assertEqual(clip.content, self.path.read_bytes())
        self.assertEqual(clip.content_type, "video/mp4")
        self.assertEqual(clip.camera_id, "camera-passageway")

    def test_unsupported_question_abstains_and_clip_requires_store_access(self) -> None:
        self.slice.process(self.source, tuple(range(10)))
        unsupported = self.api.ask(
            self.allowed, self.source.source_id, "How many red baskets are visible?"
        )
        self.assertEqual(unsupported.state, AnswerState.UNSUPPORTED)
        self.assertIsNotNone(unsupported.abstention)

        supported = self.api.ask(self.allowed, self.source.source_id, "Is a person walking?")
        denied = AuthorizationContext("operator-2", frozenset({"store-2"}))
        with self.assertRaises(AuthorizationError):
            self.api.get_citation_clip(denied, supported.citations[0].citation_id)

    def test_replay_recovers_a_missing_index_without_rerunning_the_model(self) -> None:
        first = self.slice.process(self.source, tuple(range(10)))
        recovered_index = InMemoryEvidenceIndex()
        recovered_slice = VerticalSlice(
            self.storage, recovered_index, self.caption_model, EvidenceOnlyAnswerModel()
        )

        recovered = recovered_slice.process(self.source, tuple(range(10)))

        self.assertEqual(recovered.pipeline_run, first.pipeline_run)
        self.assertEqual(recovered.index_state, PersistenceState.INDEXED)
        self.assertEqual(recovered.index_count, 1)
        self.assertEqual(self.caption_model.call_count, 1)

    def test_processing_rejects_a_checksum_that_does_not_match_the_file(self) -> None:
        bad_source = Source(
            self.source.source_id, self.source.reference, self.source.media_locator,
            self.source.codec, self.source.width, self.source.height,
            self.source.nominal_frame_rate, self.source.retention_class,
            "sha256:not-the-file", self.source.frame_range, self.source.clock,
        )
        with self.assertRaisesRegex(ValueError, "checksum"):
            self.slice.process(bad_source, tuple(range(10)))


if __name__ == "__main__":
    unittest.main()
