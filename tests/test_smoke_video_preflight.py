import unittest

from scripts.preflight_smoke_video import evenly_spaced_indices


class EvenlySpacedIndicesTests(unittest.TestCase):
    def test_selection_spans_fixture_without_duplicate_indices(self) -> None:
        indices = evenly_spaced_indices(frame_count=323, selected_count=80)

        self.assertEqual(len(indices), 80)
        self.assertEqual(indices[0], 0)
        self.assertEqual(indices[-1], 322)
        self.assertEqual(len(set(indices)), 80)

    def test_exact_frame_count_selects_every_frame(self) -> None:
        self.assertEqual(
            evenly_spaced_indices(frame_count=80, selected_count=80), tuple(range(80))
        )

    def test_insufficient_frames_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "cannot select 80 distinct frames"):
            evenly_spaced_indices(frame_count=79, selected_count=80)


if __name__ == "__main__":
    unittest.main()
