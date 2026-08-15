import unittest

from retail_intelligence.adapters.nvidia.caption import RTVLMCaptionAdapter
from retail_intelligence.ports.caption import CaptionRequest, CaptionStageState, PreparedCaptionInput


class FakePreprocessor:
    def __init__(self, width=448, height=448, selected_frame_count=None):
        self.width = width
        self.height = height
        self.selected_frame_count = selected_frame_count
        self.calls = []

    def prepare(self, frames, width, height):
        self.calls.append((frames, width, height))
        count = len(frames) if self.selected_frame_count is None else self.selected_frame_count
        return PreparedCaptionInput("tensor", self.width, self.height, count)


class FakeClient:
    def __init__(self):
        self.calls = []

    def infer(self, prepared_input):
        self.calls.append(prepared_input)
        return {"caption": "A shopper enters the aisle."}


class RTVLMCaptionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.preprocessor = FakePreprocessor()
        self.client = FakeClient()
        self.adapter = RTVLMCaptionAdapter(self.preprocessor, self.client)

    def request(self, frame_count=80, selected_frame_count=80):
        return CaptionRequest(tuple(range(frame_count)), 448, 448, selected_frame_count)

    def test_baseline_is_admitted_and_records_realized_budget(self):
        outcome = self.adapter.caption(self.request())
        self.assertEqual(outcome.state, CaptionStageState.COMPLETE)
        self.assertEqual(outcome.budget.visual_tokens, 7_840)
        self.assertEqual(len(self.client.calls), 1)

    def test_planned_under_and_over_budget_never_reach_client(self):
        for frame_count in (30, 170):
            with self.subTest(frame_count=frame_count):
                client = FakeClient()
                outcome = RTVLMCaptionAdapter(FakePreprocessor(), client).caption(
                    self.request(frame_count, frame_count)
                )
                self.assertEqual(outcome.state, CaptionStageState.REJECTED)
                self.assertFalse(outcome.budget.accepted)
                self.assertEqual(client.calls, [])

    def test_realized_dimensions_are_checked_after_preprocessing(self):
        client = FakeClient()
        outcome = RTVLMCaptionAdapter(FakePreprocessor(width=1024, height=1024), client).caption(
            self.request()
        )
        self.assertEqual(outcome.state, CaptionStageState.REJECTED)
        self.assertEqual(outcome.reason, "above_maximum")
        self.assertEqual(outcome.budget.width, 1024)
        self.assertEqual(client.calls, [])

    def test_insufficient_frames_are_not_duplicated_and_record_partial(self):
        outcome = self.adapter.caption(self.request(frame_count=60))
        self.assertEqual(self.preprocessor.calls[0][0], tuple(range(60)))
        self.assertEqual(outcome.state, CaptionStageState.PARTIAL)
        self.assertEqual(outcome.budget.selected_frames, 60)
        self.assertEqual(len(self.client.calls), 1)

    def test_frame_selection_is_evenly_spaced_without_duplicates(self):
        outcome = self.adapter.caption(self.request(frame_count=160))

        selected_frames = self.preprocessor.calls[0][0]
        self.assertEqual(len(selected_frames), 80)
        self.assertEqual(selected_frames[0], 0)
        self.assertEqual(selected_frames[-1], 159)
        self.assertEqual(len(set(selected_frames)), 80)
        self.assertEqual(outcome.state, CaptionStageState.COMPLETE)

    def test_too_few_source_frames_record_partial_without_inference(self):
        outcome = self.adapter.caption(self.request(frame_count=30))
        self.assertEqual(outcome.state, CaptionStageState.PARTIAL)
        self.assertEqual(outcome.reason, "below_minimum")
        self.assertEqual(self.preprocessor.calls, [])
        self.assertEqual(self.client.calls, [])

    def test_no_source_frames_record_gap_without_inference(self):
        outcome = self.adapter.caption(self.request(frame_count=0))
        self.assertEqual(outcome.state, CaptionStageState.GAP)
        self.assertIsNone(outcome.budget)
        self.assertEqual(self.client.calls, [])

    def test_request_rejects_non_positive_dimensions_or_frame_target(self):
        for width, height, selected_count in ((0, 448, 80), (448, -1, 80), (448, 448, 0)):
            with self.subTest(values=(width, height, selected_count)), self.assertRaises(ValueError):
                CaptionRequest(("frame",), width, height, selected_count)


if __name__ == "__main__":
    unittest.main()
