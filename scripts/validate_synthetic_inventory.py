#!/usr/bin/env python3
"""Validate the committed synthetic convenience-store inventory dataset."""

from __future__ import annotations

import hashlib
import json
import math
import struct
import sys
import zlib
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_DIRECTORY = (
    REPOSITORY_ROOT / "evals" / "datasets" / "synthetic-convenience-store-v1"
)
EXPECTED_SCHEMA_VERSION = "1.0"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
REQUIRED_ITEM_FIELDS = frozenset(
    {
        "item_id", "sku", "lot_id", "name", "synthetic_brand", "category",
        "package_size", "package_dimensions_m", "storage", "price_cents",
        "quantity_on_hand", "capacity", "facings", "placed_at", "expires_on",
        "date_marking_type", "nominal_shelf_life_days", "zone_id", "fixture_id",
        "shelf_level", "position_m", "facing_vector", "image",
    }
)


def load_dataset(dataset_directory: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest = _load_json(dataset_directory / "manifest.json")
    inventory_name = manifest.get("inventory_file", "inventory.json")
    if inventory_name != "inventory.json":
        raise ValueError("manifest inventory_file must be inventory.json")
    inventory = _load_json(dataset_directory / inventory_name)
    return manifest, inventory


def validate_dataset(dataset_directory: Path = DEFAULT_DATASET_DIRECTORY) -> list[str]:
    try:
        manifest, inventory = load_dataset(dataset_directory)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        return [str(error)]
    return validate_documents(manifest, inventory, dataset_directory)


def validate_documents(
    manifest: dict[str, Any], inventory: dict[str, Any], dataset_directory: Path
) -> list[str]:
    errors: list[str] = []
    _validate_identity(manifest, inventory, errors)
    as_of = _parse_datetime(manifest.get("as_of"), "manifest.as_of", errors)
    coordinate_system = manifest.get("coordinate_system")
    if isinstance(coordinate_system, dict):
        store_bounds = _number_vector(
            coordinate_system.get("store_bounds_m"),
            "manifest.coordinate_system.store_bounds_m",
            errors,
            positive=True,
        )
    else:
        errors.append("manifest.coordinate_system must be an object")
        store_bounds = None
    fixtures = _validate_fixtures(manifest.get("fixtures"), store_bounds, errors)

    items = inventory.get("items")
    if not isinstance(items, list) or not items:
        errors.append("inventory.items must be a non-empty array")
        return errors

    seen_ids: set[str] = set()
    seen_skus: set[str] = set()
    seen_lot_ids: set[str] = set()
    referenced_images: set[str] = set()
    for index, item in enumerate(items):
        label = f"inventory.items[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{label} must be an object")
            continue
        _validate_item(
            item,
            label,
            as_of,
            store_bounds,
            fixtures,
            dataset_directory,
            seen_ids,
            seen_skus,
            seen_lot_ids,
            referenced_images,
            errors,
        )

    expected_item_count = manifest.get("expected_item_count")
    if _is_integer(expected_item_count) and len(items) != expected_item_count:
        errors.append(
            f"inventory.items must contain {expected_item_count} records, found {len(items)}"
        )
    expected_image_count = manifest.get("expected_image_count")
    if _is_integer(expected_image_count) and len(referenced_images) != expected_image_count:
        errors.append(
            f"inventory must reference {expected_image_count} unique images, "
            f"found {len(referenced_images)}"
        )

    image_directory = dataset_directory / "images"
    if image_directory.is_dir():
        actual_images = {
            path.relative_to(dataset_directory).as_posix()
            for path in image_directory.iterdir()
            if path.is_file() and path.suffix.casefold() == ".png"
        }
        for path in sorted(actual_images - referenced_images):
            errors.append(f"unreferenced image file: {path}")
        for path in sorted(referenced_images - actual_images):
            errors.append(f"referenced image file is missing: {path}")
    else:
        errors.append(f"image directory is missing: {image_directory}")
    return errors


def _validate_identity(
    manifest: dict[str, Any], inventory: dict[str, Any], errors: list[str]
) -> None:
    for name, document in (("manifest", manifest), ("inventory", inventory)):
        if document.get("schema_version") != EXPECTED_SCHEMA_VERSION:
            errors.append(f"{name}.schema_version must be {EXPECTED_SCHEMA_VERSION}")
    dataset_id = manifest.get("dataset_id")
    if not isinstance(dataset_id, str) or not dataset_id.strip():
        errors.append("manifest.dataset_id must be non-empty text")
    if inventory.get("dataset_id") != dataset_id:
        errors.append("inventory.dataset_id must match manifest.dataset_id")
    if manifest.get("synthetic") is not True:
        errors.append("manifest.synthetic must be true")
    if manifest.get("inventory_file") != "inventory.json":
        errors.append("manifest.inventory_file must be inventory.json")
    if manifest.get("image_directory") != "images":
        errors.append("manifest.image_directory must be images")
    _positive_integer(
        manifest.get("expected_item_count"), "manifest.expected_item_count", errors
    )
    _positive_integer(
        manifest.get("expected_image_count"), "manifest.expected_image_count", errors
    )


def _validate_fixtures(
    value: Any, store_bounds: list[float] | None, errors: list[str]
) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list) or not value:
        errors.append("manifest.fixtures must be a non-empty array")
        return {}
    fixtures: dict[str, dict[str, Any]] = {}
    for index, fixture in enumerate(value):
        label = f"manifest.fixtures[{index}]"
        if not isinstance(fixture, dict):
            errors.append(f"{label} must be an object")
            continue
        fixture_id = _required_text(fixture, "fixture_id", label, errors)
        _required_text(fixture, "zone_id", label, errors)
        _required_text(fixture, "name", label, errors)
        bounds = fixture.get("bounds_m")
        if (
            not isinstance(bounds, list)
            or len(bounds) != 2
            or (minimum := _number_vector(bounds[0], f"{label}.bounds_m[0]", errors)) is None
            or (maximum := _number_vector(bounds[1], f"{label}.bounds_m[1]", errors)) is None
        ):
            continue
        if any(low >= high for low, high in zip(minimum, maximum)):
            errors.append(f"{label}.bounds_m minimum must be below maximum")
        if store_bounds and any(low < 0 or high > limit for low, high, limit in zip(minimum, maximum, store_bounds)):
            errors.append(f"{label}.bounds_m must be inside the store")
        fixture["_validated_bounds"] = (minimum, maximum)
        if fixture_id:
            if fixture_id in fixtures:
                errors.append(f"duplicate fixture_id: {fixture_id}")
            fixtures[fixture_id] = fixture
    return fixtures


def _validate_item(
    item: dict[str, Any],
    label: str,
    as_of: datetime | None,
    store_bounds: list[float] | None,
    fixtures: dict[str, dict[str, Any]],
    dataset_directory: Path,
    seen_ids: set[str],
    seen_skus: set[str],
    seen_lot_ids: set[str],
    referenced_images: set[str],
    errors: list[str],
) -> None:
    for field in sorted(REQUIRED_ITEM_FIELDS - item.keys()):
        errors.append(f"{label}.{field} is required")
    for field in ("item_id", "sku", "lot_id", "name", "synthetic_brand", "category"):
        _required_text(item, field, label, errors)
    _add_unique(item.get("item_id"), "item_id", seen_ids, errors)
    _add_unique(item.get("sku"), "sku", seen_skus, errors)
    _add_unique(item.get("lot_id"), "lot_id", seen_lot_ids, errors)

    for field in ("price_cents", "quantity_on_hand", "capacity", "facings", "shelf_level"):
        _positive_integer(item.get(field), f"{label}.{field}", errors, allow_zero=field == "quantity_on_hand")
    if _is_integer(item.get("quantity_on_hand")) and _is_integer(item.get("capacity")):
        if item["quantity_on_hand"] > item["capacity"]:
            errors.append(f"{label}.quantity_on_hand cannot exceed capacity")

    _validate_package(item, label, errors)
    position = _number_vector(item.get("position_m"), f"{label}.position_m", errors)
    _number_vector(item.get("facing_vector"), f"{label}.facing_vector", errors, nonzero=True)
    fixture = fixtures.get(item.get("fixture_id"))
    if fixture is None:
        errors.append(f"{label}.fixture_id is unknown")
    elif item.get("zone_id") != fixture.get("zone_id"):
        errors.append(f"{label}.zone_id does not match its fixture")
    if position and store_bounds and not _inside(position, [0.0, 0.0, 0.0], store_bounds):
        errors.append(f"{label}.position_m is outside the store bounds")
    if position and fixture and "_validated_bounds" in fixture:
        minimum, maximum = fixture["_validated_bounds"]
        if not _inside(position, minimum, maximum):
            errors.append(f"{label}.position_m is outside fixture {item.get('fixture_id')}")

    placed_at = _parse_datetime(item.get("placed_at"), f"{label}.placed_at", errors)
    if placed_at and as_of and placed_at > as_of:
        errors.append(f"{label}.placed_at cannot be after manifest.as_of")
    _validate_expiry(item, label, placed_at, errors)
    _validate_image(item.get("image"), label, dataset_directory, referenced_images, errors)


def _validate_package(item: dict[str, Any], label: str, errors: list[str]) -> None:
    size = item.get("package_size")
    if not isinstance(size, dict):
        errors.append(f"{label}.package_size must be an object")
    else:
        value = size.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
            errors.append(f"{label}.package_size.value must be positive")
        _required_text(size, "unit", f"{label}.package_size", errors)
    _number_vector(
        item.get("package_dimensions_m"),
        f"{label}.package_dimensions_m",
        errors,
        positive=True,
    )
    storage = item.get("storage")
    if not isinstance(storage, dict):
        errors.append(f"{label}.storage must be an object")
    else:
        _required_text(storage, "mode", f"{label}.storage", errors)
        temperatures = _number_vector(
            storage.get("temperature_c"), f"{label}.storage.temperature_c", errors, length=2
        )
        if temperatures and temperatures[0] >= temperatures[1]:
            errors.append(f"{label}.storage.temperature_c minimum must be below maximum")


def _validate_expiry(
    item: dict[str, Any], label: str, placed_at: datetime | None, errors: list[str]
) -> None:
    marking = item.get("date_marking_type")
    valid_markings = {"expiry", "use_by", "best_before", "quality_review", "none"}
    if marking not in valid_markings:
        errors.append(f"{label}.date_marking_type is invalid")
    expires_on = item.get("expires_on")
    shelf_life = item.get("nominal_shelf_life_days")
    if expires_on is None:
        if marking != "none" or shelf_life is not None:
            errors.append(f"{label} without an expiry must use marking 'none' and null shelf life")
        return
    try:
        expiry = date.fromisoformat(expires_on) if isinstance(expires_on, str) else None
    except ValueError:
        expiry = None
    if expiry is None:
        errors.append(f"{label}.expires_on must be an ISO date or null")
    elif placed_at and expiry < placed_at.date():
        errors.append(f"{label}.expires_on cannot be before placed_at")
    if marking == "none":
        errors.append(f"{label} with an expiry cannot use marking 'none'")
    _positive_integer(shelf_life, f"{label}.nominal_shelf_life_days", errors)


def _validate_image(
    image: Any,
    label: str,
    dataset_directory: Path,
    referenced_images: set[str],
    errors: list[str],
) -> None:
    if not isinstance(image, dict):
        errors.append(f"{label}.image must be an object")
        return
    path_text = image.get("path")
    if not _safe_image_path(path_text):
        errors.append(f"{label}.image.path must be a safe relative path under images/")
        return
    if path_text in referenced_images:
        errors.append(f"duplicate image path: {path_text}")
    referenced_images.add(path_text)
    if image.get("media_type") != "image/png" or image.get("synthetic") is not True:
        errors.append(f"{label}.image must declare a synthetic image/png")
    for field in ("width", "height"):
        _positive_integer(image.get(field), f"{label}.image.{field}", errors)
    sha256 = image.get("sha256")
    if not isinstance(sha256, str) or len(sha256) != 64 or any(c not in "0123456789abcdef" for c in sha256):
        errors.append(f"{label}.image.sha256 must be 64 lowercase hexadecimal characters")
        return
    image_path = dataset_directory / path_text
    try:
        data = image_path.read_bytes()
    except OSError:
        return
    dimensions = _validate_png(data, f"{label}.image", errors)
    if dimensions and dimensions != (image.get("width"), image.get("height")):
        errors.append(f"{label}.image dimensions do not match the PNG")
    if hashlib.sha256(data).hexdigest() != sha256:
        errors.append(f"{label}.image sha256 does not match the file")


def _load_json(path: Path) -> dict[str, Any]:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return document


def _validate_png(
    data: bytes, label: str, errors: list[str]
) -> tuple[int, int] | None:
    if not data.startswith(PNG_SIGNATURE):
        errors.append(f"{label} is not a valid PNG")
        return None

    offset = len(PNG_SIGNATURE)
    dimensions: tuple[int, int] | None = None
    compressed_parts: list[bytes] = []
    saw_iend = False
    while offset < len(data):
        if offset + 12 > len(data):
            errors.append(f"{label} contains a truncated PNG chunk")
            return None
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        chunk_end = offset + 12 + length
        if chunk_end > len(data):
            errors.append(f"{label} contains a truncated PNG chunk")
            return None
        chunk_type = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        expected_crc = struct.unpack(">I", data[offset + 8 + length : chunk_end])[0]
        if zlib.crc32(chunk_type + payload) & 0xFFFFFFFF != expected_crc:
            errors.append(f"{label} contains a PNG chunk with an invalid CRC")
            return None
        if dimensions is None and chunk_type != b"IHDR":
            errors.append(f"{label} must begin with an IHDR chunk")
            return None
        if chunk_type == b"IHDR":
            if dimensions is not None or length != 13:
                errors.append(f"{label} contains an invalid IHDR chunk")
                return None
            width, height, bit_depth, color_type, compression, filtering, interlace = (
                struct.unpack(">IIBBBBB", payload)
            )
            if (
                width <= 0
                or height <= 0
                or (bit_depth, color_type, compression, filtering, interlace)
                != (8, 6, 0, 0, 0)
            ):
                errors.append(f"{label} must be a non-interlaced 8-bit RGBA PNG")
                return None
            dimensions = (width, height)
        elif chunk_type == b"IDAT":
            compressed_parts.append(payload)
        elif chunk_type == b"IEND":
            if length != 0 or chunk_end != len(data):
                errors.append(f"{label} contains an invalid IEND chunk")
                return None
            saw_iend = True
        offset = chunk_end

    if dimensions is None or not compressed_parts or not saw_iend:
        errors.append(f"{label} is missing required PNG chunks")
        return None
    try:
        pixels = zlib.decompress(b"".join(compressed_parts))
    except zlib.error:
        errors.append(f"{label} contains invalid compressed pixel data")
        return None
    width, height = dimensions
    row_size = 1 + width * 4
    if len(pixels) != height * row_size or any(
        pixels[row * row_size] > 4 for row in range(height)
    ):
        errors.append(f"{label} contains invalid RGBA scanlines")
        return None
    return dimensions


def _required_text(value: dict[str, Any], field: str, label: str, errors: list[str]) -> str | None:
    text = value.get(field)
    if not isinstance(text, str) or not text.strip():
        errors.append(f"{label}.{field} must be non-empty text")
        return None
    return text


def _number_vector(
    value: Any,
    label: str,
    errors: list[str],
    *,
    length: int = 3,
    positive: bool = False,
    nonzero: bool = False,
) -> list[float] | None:
    if not isinstance(value, list) or len(value) != length:
        errors.append(f"{label} must be a {length}-element numeric array")
        return None
    if any(isinstance(number, bool) or not isinstance(number, (int, float)) or not math.isfinite(number) for number in value):
        errors.append(f"{label} must contain finite numbers")
        return None
    result = [float(number) for number in value]
    if positive and any(number <= 0 for number in result):
        errors.append(f"{label} must contain positive numbers")
    if nonzero and not any(result):
        errors.append(f"{label} cannot be the zero vector")
    return result


def _positive_integer(value: Any, label: str, errors: list[str], *, allow_zero: bool = False) -> None:
    minimum = 0 if allow_zero else 1
    if not _is_integer(value) or value < minimum:
        errors.append(f"{label} must be an integer of at least {minimum}")


def _is_integer(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _parse_datetime(value: Any, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str):
        errors.append(f"{label} must be an RFC 3339 timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label} must be an RFC 3339 timestamp")
        return None
    if parsed.utcoffset() is None:
        errors.append(f"{label} must include a UTC offset")
        return None
    return parsed


def _add_unique(value: Any, name: str, seen: set[str], errors: list[str]) -> None:
    if not isinstance(value, str):
        return
    if value in seen:
        errors.append(f"duplicate {name}: {value}")
    seen.add(value)


def _inside(point: list[float], minimum: list[float], maximum: list[float]) -> bool:
    return all(low <= coordinate <= high for coordinate, low, high in zip(point, minimum, maximum))


def _safe_image_path(value: Any) -> bool:
    if not isinstance(value, str) or "\\" in value:
        return False
    path = PurePosixPath(value)
    return not path.is_absolute() and path.parts[:1] == ("images",) and ".." not in path.parts and path.suffix == ".png"


def main() -> int:
    dataset_directory = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DATASET_DIRECTORY
    errors = validate_dataset(dataset_directory)
    if errors:
        for error in errors:
            print(f"FAIL: {error}")
        return 1
    manifest, inventory = load_dataset(dataset_directory)
    item_count = len(inventory["items"])
    image_count = len(list((dataset_directory / manifest["image_directory"]).glob("*.png")))
    print(
        f"PASS: {manifest['dataset_id']} "
        f"({item_count} items, {image_count} verified PNG images)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
