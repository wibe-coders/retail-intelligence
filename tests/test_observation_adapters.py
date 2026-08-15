import json
import unittest
from pathlib import Path

from retail_intelligence.adapters.nvidia.observations import (
    NormalizationError,
    normalize_rt_cv,
    normalize_rt_vlm,
)
from retail_intelligence.domain.intelligence import ObservationKind


FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture(name: str) -> dict:
    with (FIXTURES / name).open(encoding="utf-8") as fixture:
        return json.load(fixture)


class ObservationAdapterContractTests(unittest.TestCase):
    def test_rt_cv_normalizes_boxes_tracks_and_preserves_metadata(self) -> None:
        observations = normalize_rt_cv(load_fixture("rt_cv_observations.json"))

        self.assertEqual([item.kind for item in observations], [
            ObservationKind.BOX, ObservationKind.TRACK, ObservationKind.BOX
        ])
        unknown_box = json.loads(observations[2].value)
        self.assertEqual(unknown_box["class"], "vendor_class_987")
        self.assertIsNone(observations[2].context.confidence)
        first = observations[0]
        self.assertEqual(first.context.provenance.model, "rt-detr")
        self.assertEqual(first.context.provenance.model_version, "1.4.0")
        self.assertEqual(first.context.provenance.configuration_id, "cv-config-7")
        self.assertEqual(first.context.provenance.pipeline_run_id, "run-12")
        self.assertEqual(first.context.source.camera_id, "camera-2")
        self.assertEqual(first.context.evidence[0].frame_range.start, 300)
        self.assertEqual(first.vendor_output_reference, "vendor-output://sanitized/rt-cv-window-6")

    def test_rt_vlm_normalizes_caption_without_claiming_confidence(self) -> None:
        caption = normalize_rt_vlm(load_fixture("rt_vlm_caption.json"))[0]

        self.assertEqual(caption.kind, ObservationKind.CAPTION)
        self.assertEqual(caption.value, "A person walks through the aisle.")
        self.assertIsNone(caption.context.confidence)
        self.assertEqual(caption.context.evidence[0].time_range.end.isoformat(), "2026-08-15T07:00:10+00:00")

    def test_malformed_output_names_the_failed_stage(self) -> None:
        malformed = load_fixture("rt_cv_observations.json")
        malformed["detections"][0]["box"] = [10, 20, 5, 30]

        with self.assertRaisesRegex(NormalizationError, "rt-cv normalization failed"):
            normalize_rt_cv(malformed)

    def test_unsafe_vendor_payload_reference_is_rejected(self) -> None:
        unsafe = load_fixture("rt_vlm_caption.json")
        unsafe["payload_reference"] = "https://user:secret@example.test/frame.jpg?signature=secret"

        with self.assertRaisesRegex(NormalizationError, "rt-vlm normalization failed"):
            normalize_rt_vlm(unsafe)


if __name__ == "__main__":
    unittest.main()
