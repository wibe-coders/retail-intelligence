import json
import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from retail_intelligence.domain.intelligence import (
    EvidenceLink,
    EvidenceRecord,
    IntelligenceContext,
    Observation,
    ObservationKind,
    PersistenceState,
    PipelineProvenance,
)
from retail_intelligence.domain.media import (
    Completeness,
    EvidenceWindow,
    RetentionClass,
    SourceReference,
    TimeRange,
)
from retail_intelligence.domain.query import Abstention, Answer, AnswerState, Citation


class DomainContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.start = datetime(2026, 8, 15, 7, 0, tzinfo=timezone.utc)
        self.interval = TimeRange(self.start, self.start + timedelta(seconds=10))
        self.source = SourceReference("store-1", "camera-2", "recording-3")
        self.provenance = PipelineProvenance(
            "rt-vlm", "3.2.1", "config-4", (("prompt_revision", "sha256:abc"),), "run-5"
        )
        self.evidence = EvidenceLink(
            self.source, "window-6", self.interval, None, "media://recording-3"
        )
        self.context = IntelligenceContext(
            self.source,
            self.provenance,
            (self.evidence,),
            0.75,
            self.start + timedelta(seconds=11),
            RetentionClass.STANDARD,
        )

    def test_time_range_requires_non_empty_utc_half_open_interval(self) -> None:
        invalid_ranges = (
            (self.start, self.start),
            (self.start, self.start - timedelta(seconds=1)),
            (self.start.replace(tzinfo=None), self.start + timedelta(seconds=1)),
            (
                self.start.astimezone(timezone(timedelta(hours=1))),
                self.start.astimezone(timezone(timedelta(hours=1))) + timedelta(seconds=1),
            ),
        )
        for start, end in invalid_ranges:
            with self.subTest(start=start, end=end), self.assertRaises(ValueError):
                TimeRange(start, end)

    def test_required_source_identifiers_fail_visibly(self) -> None:
        invalid_identifiers = (
            ("", "camera", "recording"),
            ("store", " ", "recording"),
            ("store", "camera", ""),
        )
        for values in invalid_identifiers:
            with self.subTest(values=values), self.assertRaises(ValueError):
                SourceReference(*values)

    def test_evidence_window_round_trips_as_framework_independent_json(self) -> None:
        window = EvidenceWindow(
            "window-6", self.source, self.interval, None, 300, 250,
            "pipeline-1", "config-4", Completeness.PARTIAL,
        )
        serialized = window.to_json()

        self.assertEqual(EvidenceWindow.from_json(serialized), window)
        self.assertIsInstance(json.loads(serialized), dict)

    def test_completeness_must_match_observed_frame_counts(self) -> None:
        invalid_states = (
            (300, 299, Completeness.COMPLETE),
            (300, 0, Completeness.PARTIAL),
            (300, 1, Completeness.GAP),
        )
        for expected, observed, completeness in invalid_states:
            with self.subTest(completeness=completeness), self.assertRaises(ValueError):
                EvidenceWindow(
                    "window-6",
                    self.source,
                    self.interval,
                    None,
                    expected,
                    observed,
                    "pipeline-1",
                    "config-4",
                    completeness,
                )

    def test_caption_is_an_observation_with_complete_provenance(self) -> None:
        caption = Observation(
            "observation-7", ObservationKind.CAPTION, "A person enters the aisle.",
            self.context, "vendor-output://7",
        )

        self.assertEqual(caption.kind, ObservationKind.CAPTION)
        self.assertEqual(caption.context.source, self.source)
        self.assertEqual(caption.context.provenance.pipeline_run_id, "run-5")
        self.assertEqual(Observation.from_json(caption.to_json()), caption)
        with self.assertRaises(FrozenInstanceError):
            caption.value = "fact"  # type: ignore[misc]

    def test_confidence_boundary_is_inclusive_and_out_of_range_fails(self) -> None:
        for confidence in (0.0, 1.0):
            context = IntelligenceContext(
                self.source, self.provenance, (self.evidence,), confidence,
                self.start, RetentionClass.TRANSIENT,
            )
            self.assertEqual(context.confidence, confidence)
        with self.assertRaises(ValueError):
            IntelligenceContext(
                self.source, self.provenance, (self.evidence,), 1.01,
                self.start, RetentionClass.TRANSIENT,
            )
        for confidence in (float("nan"), float("inf")):
            with self.subTest(confidence=confidence), self.assertRaises(ValueError):
                IntelligenceContext(
                    self.source,
                    self.provenance,
                    (self.evidence,),
                    confidence,
                    self.start,
                    RetentionClass.TRANSIENT,
                )

    def test_evidence_record_preserves_partial_stage_and_storage_status(self) -> None:
        window = EvidenceWindow(
            "window-6",
            self.source,
            self.interval,
            None,
            300,
            250,
            "pipeline-1",
            "config-4",
            Completeness.PARTIAL,
        )
        caption = Observation(
            "observation-7",
            ObservationKind.CAPTION,
            "A person enters the aisle.",
            self.context,
            "vendor-output://7",
        )
        record = EvidenceRecord(
            window,
            (caption,),
            (),
            ("tracking",),
            PersistenceState.STORED,
            PersistenceState.PENDING,
            None,
        )

        self.assertEqual(EvidenceRecord.from_json(record.to_json()), record)
        self.assertEqual(record.missing_stages, ("tracking",))

    def test_complete_evidence_record_rejects_missing_stages(self) -> None:
        window = EvidenceWindow(
            "window-6",
            self.source,
            self.interval,
            None,
            300,
            300,
            "pipeline-1",
            "config-4",
            Completeness.COMPLETE,
        )
        with self.assertRaises(ValueError):
            EvidenceRecord(
                window,
                (),
                (),
                ("captioning",),
                PersistenceState.STORED,
                PersistenceState.PENDING,
                None,
            )

    def test_answer_states_encode_support_and_each_abstention(self) -> None:
        citation = Citation("citation-1", self.evidence, "A person entered the aisle.")
        supported = Answer(
            "answer-1", AnswerState.SUPPORTED, "A person entered.", 0.8, (citation,), None
        )
        self.assertEqual(Answer.from_json(supported.to_json()), supported)

        for state in (
            AnswerState.AMBIGUOUS,
            AnswerState.UNSUPPORTED,
            AnswerState.OUT_OF_RETENTION,
        ):
            answer = Answer("answer-2", state, None, None, (), Abstention(state, "No usable evidence."))
            with self.subTest(state=state):
                self.assertEqual(Answer.from_dict(answer.to_dict()), answer)

    def test_supported_answer_without_citation_and_mismatched_abstention_fail(self) -> None:
        with self.assertRaises(ValueError):
            Answer("answer-1", AnswerState.SUPPORTED, "Uncited", 0.5, (), None)
        with self.assertRaises(ValueError):
            Answer(
                "answer-2", AnswerState.AMBIGUOUS, None, None, (),
                Abstention(AnswerState.UNSUPPORTED, "No evidence."),
            )


if __name__ == "__main__":
    unittest.main()
