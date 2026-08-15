import unittest
from dataclasses import FrozenInstanceError

from retail_intelligence.inference_budget import evaluate_inference_budget


class EvaluateInferenceBudgetTests(unittest.TestCase):
    def test_baseline_budget_is_accepted(self) -> None:
        budget = evaluate_inference_budget(width=448, height=448, selected_frames=80)

        self.assertEqual(budget.width, 448)
        self.assertEqual(budget.height, 448)
        self.assertEqual(budget.selected_frames, 80)
        self.assertEqual(budget.visual_tokens, 7_840)
        self.assertTrue(budget.accepted)
        self.assertIsNone(budget.rejection_reason)

    def test_budget_below_minimum_is_rejected(self) -> None:
        budget = evaluate_inference_budget(width=448, height=448, selected_frames=30)

        self.assertEqual(budget.visual_tokens, 2_940)
        self.assertFalse(budget.accepted)
        self.assertEqual(budget.rejection_reason, "below_minimum")

    def test_budget_above_maximum_is_rejected(self) -> None:
        budget = evaluate_inference_budget(width=448, height=448, selected_frames=170)

        self.assertEqual(budget.visual_tokens, 16_660)
        self.assertFalse(budget.accepted)
        self.assertEqual(budget.rejection_reason, "above_maximum")

    def test_odd_frame_count_uses_ceiling_division(self) -> None:
        odd = evaluate_inference_budget(width=448, height=448, selected_frames=41)
        even = evaluate_inference_budget(width=448, height=448, selected_frames=42)

        self.assertEqual(odd.visual_tokens, 4_116)
        self.assertEqual(odd.visual_tokens, even.visual_tokens)

    def test_dimension_above_patch_boundary_uses_another_patch(self) -> None:
        on_boundary = evaluate_inference_budget(width=32, height=32, selected_frames=4_096)
        above_boundary = evaluate_inference_budget(width=33, height=32, selected_frames=4_096)

        self.assertEqual(on_boundary.visual_tokens, 2_048)
        self.assertEqual(above_boundary.visual_tokens, 4_096)

    def test_acceptance_limits_are_inclusive(self) -> None:
        minimum = evaluate_inference_budget(width=32, height=32, selected_frames=8_192)
        maximum = evaluate_inference_budget(width=32, height=32, selected_frames=32_768)

        self.assertTrue(minimum.accepted)
        self.assertTrue(maximum.accepted)

    def test_non_positive_inputs_raise_value_error(self) -> None:
        invalid_inputs = (
            (0, 448, 80),
            (-1, 448, 80),
            (448, 0, 80),
            (448, -1, 80),
            (448, 448, 0),
            (448, 448, -1),
        )

        for width, height, selected_frames in invalid_inputs:
            with self.subTest(
                width=width, height=height, selected_frames=selected_frames
            ):
                with self.assertRaises(ValueError):
                    evaluate_inference_budget(width, height, selected_frames)

    def test_result_is_immutable(self) -> None:
        budget = evaluate_inference_budget(width=448, height=448, selected_frames=80)

        with self.assertRaises(FrozenInstanceError):
            budget.accepted = False  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
