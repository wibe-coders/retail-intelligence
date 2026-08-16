import copy
import tempfile
import unittest
import xml.etree.ElementTree as ElementTree
from pathlib import Path

from scripts.render_synthetic_floor_map import (
    generate_floor_maps,
    project_position,
    render_html,
    render_svg,
)
from scripts.validate_synthetic_inventory import load_dataset


DATASET_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "evals"
    / "datasets"
    / "synthetic-convenience-store-v1"
)


class SyntheticFloorMapTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest, self.inventory = load_dataset(DATASET_DIRECTORY)

    def test_projection_keeps_left_right_and_places_rear_at_top(self) -> None:
        self.assertEqual(project_position([0.0, 0.0, 2.0], 10.8), (70.0, 664.0))
        self.assertEqual(project_position([6.6, 10.8, 0.0], 10.8), (433.0, 70.0))

    def test_svg_is_parseable_and_contains_every_authored_object(self) -> None:
        svg = render_svg(self.manifest, self.inventory)

        root = ElementTree.fromstring(svg)
        self.assertEqual(root.tag, "{http://www.w3.org/2000/svg}svg")
        for fixture in self.manifest["fixtures"]:
            self.assertIn(f'data-fixture-id="{fixture["fixture_id"]}"', svg)
        for feature in self.manifest["layout_features"]:
            self.assertIn(f'data-feature-id="{feature["feature_id"]}"', svg)
        for item in self.inventory["items"]:
            self.assertIn(f'data-item-id="{item["item_id"]}"', svg)

    def test_item_order_does_not_change_rendered_outputs(self) -> None:
        shuffled = copy.deepcopy(self.inventory)
        shuffled["items"].reverse()

        expected_svg = render_svg(self.manifest, self.inventory)
        self.assertEqual(render_svg(self.manifest, shuffled), expected_svg)
        self.assertEqual(
            render_html(self.manifest, shuffled, expected_svg),
            render_html(self.manifest, self.inventory, expected_svg),
        )

    def test_exact_xy_stack_draws_highest_z_last(self) -> None:
        stacked = copy.deepcopy(self.inventory)
        lower = copy.deepcopy(stacked["items"][0])
        upper = copy.deepcopy(stacked["items"][0])
        lower.update(item_id="stack-lower", sku="STACK-LOWER", position_m=[1.0, 1.0, 0.2])
        upper.update(item_id="stack-upper", sku="STACK-UPPER", position_m=[1.0, 1.0, 1.8])
        stacked["items"] = [upper, lower]

        svg = render_svg(self.manifest, stacked)

        self.assertLess(
            svg.index('data-item-id="stack-lower"'),
            svg.index('data-item-id="stack-upper"'),
        )

    def test_inventory_text_is_escaped_in_svg_and_script_data(self) -> None:
        adversarial = copy.deepcopy(self.inventory)
        adversarial["items"][0]["name"] = '</script><svg onload="alert(1)">&'

        svg = render_svg(self.manifest, adversarial)
        document = render_html(self.manifest, adversarial, svg)

        ElementTree.fromstring(svg)
        self.assertNotIn('</script><svg onload="alert(1)">', document)
        self.assertIn("&lt;/script&gt;&lt;svg", svg)

    def test_committed_maps_are_exact_renderer_outputs(self) -> None:
        expected_svg = render_svg(self.manifest, self.inventory)
        expected_html = render_html(self.manifest, self.inventory, expected_svg)

        self.assertEqual(
            (DATASET_DIRECTORY / "floor-map.svg").read_text(encoding="utf-8"),
            expected_svg,
        )
        self.assertEqual(
            (DATASET_DIRECTORY / "floor-map.html").read_text(encoding="utf-8"),
            expected_html,
        )

    def test_generator_writes_requested_output_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            destination = Path(temporary_directory)
            svg_path, html_path = generate_floor_maps(
                DATASET_DIRECTORY,
                destination / "map.svg",
                destination / "map.html",
            )

            self.assertTrue(svg_path.is_file())
            self.assertTrue(html_path.is_file())


if __name__ == "__main__":
    unittest.main()
