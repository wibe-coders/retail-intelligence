import unittest
from datetime import datetime, timedelta, timezone

from retail_intelligence.adapters.storage import ConflictingRecordError, InMemoryEvidenceStorage
from retail_intelligence.domain.intelligence import (
    EvidenceLink,
    Event,
    IntelligenceContext,
    Observation,
    ObservationKind,
    PipelineProvenance,
    PipelineRun,
    PipelineRunState,
)
from retail_intelligence.domain.media import (
    Completeness,
    EvidenceWindow,
    RetentionClass,
    Source,
    SourceReference,
    TimeRange,
)
from retail_intelligence.domain.query import Citation


class InMemoryEvidenceStorageTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = InMemoryEvidenceStorage()
        self.start = datetime(2026, 8, 15, 12, tzinfo=timezone.utc)
        self.interval = TimeRange(self.start, self.start + timedelta(seconds=10))
        self.reference = SourceReference("store-1", "camera-1", "recording-1")
        self.other_store_reference = SourceReference("store-2", "camera-1", "recording-1")

    def source(self, source_id: str, reference: SourceReference) -> Source:
        return Source(
            source_id, reference, "media://recording", "h264", 1920, 1080, 30,
            RetentionClass.STANDARD,
        )

    def window(self, window_id: str, reference: SourceReference) -> EvidenceWindow:
        return EvidenceWindow(
            window_id, reference, self.interval, None, 300, 300,
            "pipeline-1", "config-1", Completeness.COMPLETE,
        )

    def context(self, reference: SourceReference, window_id: str) -> IntelligenceContext:
        link = EvidenceLink(reference, window_id, self.interval, None, "media://recording")
        provenance = PipelineProvenance("model", "1", "config-1", (), "run-1")
        return IntelligenceContext(
            reference, provenance, (link,), 0.9,
            self.start + timedelta(seconds=10), RetentionClass.STANDARD,
        )

    def test_empty_temporal_queries_return_immutable_empty_results(self) -> None:
        query = TimeRange(self.start, self.start + timedelta(minutes=1))

        self.assertEqual(self.storage.find_evidence_windows(self.reference, query), ())
        self.assertEqual(self.storage.find_observations(self.reference, query), ())
        self.assertEqual(self.storage.find_events(self.reference, query), ())
        self.assertEqual(self.storage.find_citations(self.reference, query), ())

    def test_resaving_equal_record_is_idempotent_and_conflict_fails(self) -> None:
        original = self.source("source-1", self.reference)
        self.assertEqual(self.storage.save_source(original), original)
        self.assertEqual(self.storage.save_source(original), original)

        conflicting = Source(
            "source-1", self.reference, "media://changed", "h264",
            1920, 1080, 30, RetentionClass.STANDARD,
        )
        with self.assertRaises(ConflictingRecordError):
            self.storage.save_source(conflicting)

        self.assertEqual(self.storage.get_source("source-1"), original)

    def test_queries_isolate_stores_and_use_half_open_time_ranges(self) -> None:
        own = self.window("window-1", self.reference)
        other = self.window("window-2", self.other_store_reference)
        self.storage.save_evidence_window(other)
        self.storage.save_evidence_window(own)

        overlapping = TimeRange(
            self.start + timedelta(seconds=5), self.start + timedelta(seconds=15)
        )
        touching_end = TimeRange(self.interval.end, self.interval.end + timedelta(seconds=1))

        self.assertEqual(self.storage.find_evidence_windows(self.reference, overlapping), (own,))
        self.assertEqual(self.storage.find_evidence_windows(self.reference, touching_end), ())

    def test_observations_events_and_citations_are_scoped_and_deterministic(self) -> None:
        context = self.context(self.reference, "window-1")
        observation_b = Observation(
            "observation-b", ObservationKind.CAPTION, "B", context, "vendor://b"
        )
        observation_a = Observation(
            "observation-a", ObservationKind.CAPTION, "A", context, "vendor://a"
        )
        event = Event("event-1", "entry", ("observation-a",), context.provenance, context)
        citation = Citation("citation-1", context.evidence[0], "A person entered.")
        for observation in (observation_b, observation_a):
            self.storage.save_observation(observation)
        self.storage.save_event(event)
        self.storage.save_citation(citation)

        self.assertEqual(
            self.storage.find_observations(self.reference, self.interval),
            (observation_a, observation_b),
        )
        self.assertEqual(self.storage.find_events(self.reference, self.interval), (event,))
        self.assertEqual(self.storage.find_citations(self.reference, self.interval), (citation,))
        self.assertEqual(
            self.storage.find_observations(self.other_store_reference, self.interval),
            (),
        )

    def test_pipeline_runs_are_queryable_by_source_and_utc_range(self) -> None:
        run = PipelineRun(
            "run-1", self.reference, self.interval, "pipeline-1", "config-1",
            PipelineRunState.SUCCEEDED,
        )
        self.storage.save_pipeline_run(run)

        self.assertEqual(self.storage.get_pipeline_run("run-1"), run)
        self.assertEqual(self.storage.find_pipeline_runs(self.reference, self.interval), (run,))
        self.assertEqual(
            self.storage.find_pipeline_runs(self.other_store_reference, self.interval),
            (),
        )


if __name__ == "__main__":
    unittest.main()
