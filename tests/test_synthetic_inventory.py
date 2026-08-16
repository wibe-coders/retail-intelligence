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
        self.assertEqual(
            {item["image"]["path"] for item in self.inventory["items"]},
            {
                path.relative_to(DATASET_DIRECTORY).as_posix()
                for path in (DATASET_DIRECTORY / "images").glob("*.png")
            },
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
