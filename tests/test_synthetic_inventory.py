import copy
import struct
import unittest
import zlib
from pathlib import Path

from scripts.validate_synthetic_inventory import (
    PNG_SIGNATURE,
    _validate_png,
    load_dataset,
    validate_dataset,
    validate_documents,
)


DATASET_DIRECTORY = (
    Path(__file__).resolve().parents[1]
    / "evals"
    / "datasets"
    / "synthetic-convenience-store-v1"
)


class SyntheticInventoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.manifest, self.inventory = load_dataset(DATASET_DIRECTORY)

    def validate_mutation(self, change) -> list[str]:
        manifest = copy.deepcopy(self.manifest)
        inventory = copy.deepcopy(self.inventory)
        change(manifest, inventory)
        return validate_documents(manifest, inventory, DATASET_DIRECTORY)

    def test_committed_dataset_and_images_are_valid(self) -> None:
        self.assertEqual(validate_dataset(DATASET_DIRECTORY), [])
        self.assertEqual(len(self.inventory["items"]), 24)
        self.assertEqual(self.manifest["expected_item_count"], 24)
        self.assertEqual(self.manifest["expected_image_count"], 24)
        self.assertEqual(len(self.manifest["fixtures"]), 6)
        self.assertEqual(len(self.manifest["layout_features"]), 2)
        self.assertEqual(
            self.manifest["coordinate_system"]["store_bounds_m"],
            [6.6, 10.8, 3.0],
        )
        fixture_ids = {fixture["fixture_id"] for fixture in self.manifest["fixtures"]}
        self.assertEqual(
            {fixture_id for fixture_id in fixture_ids if fixture_id.startswith("gondola-")},
            {"gondola-a", "gondola-b"},
        )
        self.assertNotIn("prepared-food", fixture_ids)
        self.assertNotIn("fresh-island", fixture_ids)
        self.assertNotIn("right-wall", fixture_ids)
        self.assertNotIn("fresh-wall", fixture_ids)
        self.assertIn("fresh-front", fixture_ids)
        fresh_food = [
            item
            for item in self.inventory["items"]
            if item["category"] in {"fresh-food", "fresh-produce", "fresh-bakery"}
        ]
        self.assertEqual(
            {item["fixture_id"] for item in fresh_food},
            {"fresh-front"},
        )
        essentials = [
            item
            for item in self.inventory["items"]
            if item["category"]
            in {"health", "travel-needs", "electronics-accessory", "household"}
        ]
        self.assertEqual(
            {item["fixture_id"] for item in essentials},
            {"gondola-b"},
        )
        self.assertEqual(
            {item["image"]["path"] for item in self.inventory["items"]},
            {
                path.relative_to(DATASET_DIRECTORY).as_posix()
                for path in (DATASET_DIRECTORY / "images").glob("*.png")
            },
        )

    def test_compact_layout_retains_walkable_fixture_clearances(self) -> None:
        fixtures = {
            fixture["fixture_id"]: fixture["bounds_m"]
            for fixture in self.manifest["fixtures"]
        }

        self.assertAlmostEqual(
            fixtures["gondola-a"][0][0] - fixtures["left-cold"][1][0], 0.95
        )
        self.assertAlmostEqual(
            fixtures["gondola-b"][0][0] - fixtures["gondola-a"][1][0], 1.25
        )
        self.assertAlmostEqual(
            fixtures["rear-cold"][0][1] - fixtures["gondola-a"][1][1], 1.15
        )
        self.assertAlmostEqual(
            fixtures["gondola-a"][0][1] - fixtures["checkout-rack"][1][1], 1.35
        )
        self.assertAlmostEqual(
            fixtures["checkout-rack"][0][0] - fixtures["fresh-front"][1][0], 0.2
        )
        self.assertAlmostEqual(
            self.manifest["coordinate_system"]["store_bounds_m"][0]
            - fixtures["gondola-b"][1][0],
            1.45,
        )

    def test_position_outside_store_and_fixture_is_rejected(self) -> None:
        errors = self.validate_mutation(
            lambda _manifest, inventory: inventory["items"][0].update(
                position_m=[11.1, 12.5, 0.688]
            )
        )

        self.assertTrue(any("outside the store bounds" in error for error in errors))
        self.assertTrue(any("outside fixture rear-cold" in error for error in errors))

    def test_expiry_before_placement_is_rejected(self) -> None:
        errors = self.validate_mutation(
            lambda _manifest, inventory: inventory["items"][12].update(
                expires_on="2026-08-14"
            )
        )

        self.assertTrue(any("expires_on cannot be before placed_at" in error for error in errors))

    def test_duplicate_item_identifier_is_rejected(self) -> None:
        errors = self.validate_mutation(
            lambda _manifest, inventory: inventory["items"][1].update(
                item_id=inventory["items"][0]["item_id"]
            )
        )

        self.assertIn("duplicate item_id: inv-001", errors)

    def test_duplicate_lot_identifier_is_rejected(self) -> None:
        errors = self.validate_mutation(
            lambda _manifest, inventory: inventory["items"][1].update(
                lot_id=inventory["items"][0]["lot_id"]
            )
        )

        self.assertIn("duplicate lot_id: LOT-BEV-001-2607", errors)

    def test_fixed_item_count_is_enforced(self) -> None:
        errors = self.validate_mutation(
            lambda _manifest, inventory: inventory["items"].pop()
        )

        self.assertTrue(any("must contain 24 records, found 23" in error for error in errors))

    def test_each_item_requires_a_unique_image(self) -> None:
        def share_image(_manifest, inventory) -> None:
            inventory["items"][1]["image"] = copy.deepcopy(
                inventory["items"][0]["image"]
            )

        errors = self.validate_mutation(share_image)

        self.assertIn("duplicate image path: images/syn-bev-001.png", errors)
        self.assertTrue(any("must reference 24 unique images" in error for error in errors))

    def test_coordinate_system_must_be_an_object(self) -> None:
        errors = self.validate_mutation(
            lambda manifest, _inventory: manifest.update(coordinate_system=None)
        )

        self.assertIn("manifest.coordinate_system must be an object", errors)

    def test_layout_feature_must_stay_inside_store(self) -> None:
        errors = self.validate_mutation(
            lambda manifest, _inventory: manifest["layout_features"][0][
                "footprint_m"
            ].__setitem__(0, [12.0, 0.0])
        )

        self.assertTrue(any("footprint_m must be inside the store" in error for error in errors))

    def test_layout_feature_cannot_self_intersect(self) -> None:
        errors = self.validate_mutation(
            lambda manifest, _inventory: manifest["layout_features"][0].update(
                footprint_m=[[8.0, 0.0], [10.0, 1.0], [8.0, 1.0], [10.0, 0.0]]
            )
        )

        self.assertTrue(any("footprint_m cannot self-intersect" in error for error in errors))

    def test_truncated_png_structure_is_rejected(self) -> None:
        ihdr_payload = struct.pack(">IIBBBBB", 512, 512, 8, 6, 0, 0, 0)
        ihdr_type = b"IHDR"
        ihdr = (
            struct.pack(">I", len(ihdr_payload))
            + ihdr_type
            + ihdr_payload
            + struct.pack(">I", zlib.crc32(ihdr_type + ihdr_payload) & 0xFFFFFFFF)
        )
        errors: list[str] = []

        self.assertIsNone(_validate_png(PNG_SIGNATURE + ihdr, "image", errors))
        self.assertIn("image is missing required PNG chunks", errors)

    def test_image_path_cannot_escape_dataset(self) -> None:
        errors = self.validate_mutation(
            lambda _manifest, inventory: inventory["items"][0]["image"].update(
                path="images/../../reatil_711.png"
            )
        )

        self.assertTrue(any("safe relative path" in error for error in errors))

    def test_image_checksum_tampering_is_rejected(self) -> None:
        errors = self.validate_mutation(
            lambda _manifest, inventory: inventory["items"][0]["image"].update(
                sha256="0" * 64
            )
        )

        self.assertTrue(any("sha256 does not match" in error for error in errors))


if __name__ == "__main__":
    unittest.main()
