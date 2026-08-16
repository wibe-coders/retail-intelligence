import unittest
from datetime import datetime, timezone

from retail_intelligence.adapters.storage import ConflictingRecordError, InMemoryEvidenceStorage
from retail_intelligence.domain.media import (
    Completeness,
    FrameRange,
    RetentionClass,
    Source,
    SourceClock,
    SourceReference,
)
from retail_intelligence.pipelines import FileWindowFormer, TimestampIssue


class FileIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.storage = InMemoryEvidenceStorage()
        self.former = FileWindowFormer(self.storage)
        self.clock = SourceClock(datetime(2026, 8, 16, 12, tzinfo=timezone.utc), 0, 5, 1, 2)
        self.source = Source(
            "source-1", SourceReference("store-1", "camera-1", "recording-1"),
            "file:///recordings/one.mp4", "h264", 1920, 1080, 2,
            RetentionClass.STANDARD, "sha256:abc", FrameRange(10, 16), self.clock,
        )

    def test_registration_preserves_file_metadata_and_is_idempotent(self) -> None:
        self.assertIs(self.former.register(self.source), self.source)
        self.assertEqual(self.former.register(self.source), self.source)

        stored = self.storage.get_source("source-1")
        self.assertEqual(stored.checksum, "sha256:abc")
        self.assertEqual(stored.clock, self.clock)
        self.assertEqual(stored.frame_range, FrameRange(10, 16))
        self.assertEqual(stored.retention_class, RetentionClass.STANDARD)
        self.assertEqual(Source.from_json(stored.to_json()), stored)

    def test_conflicting_duplicate_source_identifier_fails_without_replacement(self) -> None:
        self.former.register(self.source)
        conflicting = Source(
            "source-1", self.source.reference, self.source.media_locator, "hevc",
            1280, 720, 24, RetentionClass.ARCHIVE, "sha256:different",
            FrameRange(10, 16), self.clock,
        )
        with self.assertRaises(ConflictingRecordError):
            self.former.register(conflicting)
        self.assertEqual(self.storage.get_source("source-1"), self.source)

    def test_windows_use_half_open_pts_boundaries_and_expose_timestamp_faults(self) -> None:
        result = self.former.form_windows(
            self.source, (0, 2, 1, None, 4, 4), 1, "ingest-v1", {"window": 1}
        )

        self.assertEqual([window.observed_frame_count for window in result.windows], [2, 1, 2])
        self.assertEqual(
            [window.completeness for window in result.windows],
            [Completeness.COMPLETE, Completeness.PARTIAL, Completeness.PARTIAL],
        )
        self.assertEqual(result.windows[2].expected_frame_count, 1)
        self.assertEqual(result.windows[0].frame_range, FrameRange(10, 13))
        self.assertLessEqual(result.windows[0].time_range.end, result.windows[1].time_range.start)
        self.assertIn(TimestampIssue.OUT_OF_ORDER, result.frame_timestamps[2].issues)
        self.assertEqual(result.frame_timestamps[3].issues, (TimestampIssue.MISSING,))
        self.assertIn(TimestampIssue.DUPLICATE, result.frame_timestamps[5].issues)
        self.assertEqual(result.frame_timestamps[0].frame_index, 10)
        self.assertIsNone(result.frame_timestamps[3].window_id)
        self.assertEqual(result.frame_timestamps[1].window_id, result.windows[1].window_id)

        replay = self.former.form_windows(
            self.source, (0, 2, 1, None, 4, 4), 1, "ingest-v1", {"window": 1}
        )
        self.assertEqual(replay, result)

    def test_timestamp_fixture_must_cover_every_declared_source_frame(self) -> None:
        with self.assertRaisesRegex(ValueError, "timestamp count"):
            self.former.form_windows(self.source, (0, 1), 1, "ingest-v1", {"window": 1})


if __name__ == "__main__":
    unittest.main()
