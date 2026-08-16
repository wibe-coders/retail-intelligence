# Synthetic Convenience Store Inventory v1

This dataset describes 24 fictional SKU lots in a compact convenience store. It supports spatial
inventory demos and tests without asserting that the products or geometry came from a real store.
Every item has an authored 3D position, realistic retail metadata, and an original synthetic image.

The layout is inspired by an uncalibrated fisheye store image: checkout in front, refrigerated cases
at the rear, dry-goods gondolas in the center, a fresh-food island, and health/household shelves on
the right wall. A single image cannot establish metric geometry, so the 11 m × 13 m × 3 m store and
all fixture bounds are explicit modeling choices.

## Files

- `manifest.json` defines the snapshot time, coordinate system, fixtures, and provenance.
- `inventory.json` contains one SKU-lot record per row.
- `images/` contains one checksummed 512 × 512 PNG per SKU.
- `IMAGE_PROMPTS.md` records the final image-generation prompt set.
- `floor-map.svg` is the deterministic, scalable top-down map.
- `floor-map.html` adds selectable markers and product details without external dependencies.

Run the integrity, geometry, date, and image checks from the repository root:

```bash
python3 scripts/validate_synthetic_inventory.py
```

Regenerate both floor-map outputs from the repository root:

```bash
python3 -m scripts.render_synthetic_floor_map
```

## Coordinate model

`position_m` is a three-element `[x, y, z]` array locating the package centroid in meters.

- The origin is the front-left floor corner.
- `+x` runs from the left cooler wall toward the entrance and right wall.
- `+y` runs from the foreground checkout toward the rear cooler wall.
- `+z` runs from floor to ceiling.

Positions are inside the fixture named by `fixture_id`; they are not camera-calibration output. A
`facing_vector` indicates the direction the package front faces. `shelf_level` is one-based within
its fixture and is descriptive, not a globally shared height.

The floor map projects `[x, y, z]` to `[x, y]`, with the rear at the top. It draws exact x/y stacks
from lower to higher z, so the highest item remains visible. Empty fixtures and two-dimensional
entrance/circulation polygons provide context without claiming they contain inventory.

## Inventory record

Each record includes stable item, SKU, and lot identifiers; fictional name and brand; category;
package size and metric dimensions; storage mode and temperature range; price in integer cents;
stock, capacity, and facing counts; placement time; date marking; nominal shelf life; fixture, shelf,
position, and orientation; and image path, media type, dimensions, checksum, and synthetic flag.

`expires_on` uses the item's actual kind of date marking: expiry, use-by, best-before, or a quality
review date. Products that do not realistically expire, such as tissues and a charging cable, use
`null` with `date_marking_type: "none"` instead of an invented expiry.

Prices and shelf lives are plausible illustrative values for the fixed snapshot
`2026-08-15T12:00:00-07:00`. They are not current price claims, supplier data, or food-safety advice.
All brands, lots, packaging, and images are fictional.
