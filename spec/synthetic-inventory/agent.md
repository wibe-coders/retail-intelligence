# Synthetic Inventory Dataset Specification

## Authority and boundary

This document owns the committed synthetic convenience-store inventory under
`evals/datasets/synthetic-convenience-store-v1/`. It defines an evaluation and demonstration asset;
it does not add POS or inventory integration to the first-release application.

## Purpose

The dataset supplies deterministic product metadata and spatial ground truth for inventory-aware
experiments. It must remain obviously synthetic, locally verifiable, and independent of proprietary
store catalogs. The reference store image contributes only broad layout cues. Its fisheye view is
not calibrated and cannot support recovered metric coordinates.

## Snapshot and geometry contract

- `manifest.json` and `inventory.json` use schema version `1.0` and the same dataset identifier.
- The manifest fixes the expected inventory and unique-image counts for this immutable revision.
- The snapshot time is fixed and offset-aware so placement validation does not depend on wall time.
- The modeled store is 6.6 m wide, 10.8 m deep, and 3 m high.
- The origin is the front-left floor corner. Positive x moves toward the right wall, positive y
  moves from checkout to the rear coolers, and positive z moves upward.
- `position_m` is the package centroid as a three-number array in meters.
- Every position names a fixture and zone and falls inside that fixture's axis-aligned bounds.
- `facing_vector` is nonzero. `shelf_level` is a positive, fixture-local level number.
- The store has exactly two central gondolas and no prepared-food counter or fresh-food island.
- Fresh-food, produce, and bakery items use the front fresh section immediately beside checkout.
  Each item retains its realistic chilled or ambient storage mode within that mixed
  cooler-and-display fixture.
- Health, travel, electronics, and household essentials use the inward face of gondola B.
- Authored fixture clearances retain 0.95 m beside the left cooler, 1.25 m between gondolas,
  1.15 m behind the gondolas, and 1.35 m in front of them.
- No fixture occupies the right wall. The entrance-side main aisle has 1.45 m of clear width from
  gondola B to the store boundary.
- Layout features are named, simple 2D polygons inside the store. They describe entrances and
  circulation, not inventory-addressable fixtures, and may overlap other layout annotations.

## Inventory contract

Each row represents one SKU lot and contains:

- unique item, SKU, and lot identifiers;
- fictional product and brand names plus category;
- positive package size and `[width, depth, height]` dimensions in meters;
- storage mode and an increasing Celsius temperature range;
- positive integer price in cents, capacity, facings, and non-negative stock not above capacity;
- an offset-aware placement timestamp no later than the snapshot;
- an ISO expiry/date-marking date no earlier than placement, or null for non-expiring products;
- fixture, zone, shelf, position, and facing data;
- a safe relative path to one unique declared synthetic PNG with dimensions and SHA-256 checksum.

Date marking distinguishes `expiry`, `use_by`, `best_before`, `quality_review`, and `none`. A null
date requires `none` and a null nominal shelf life. This avoids presenting a made-up expiry as a
real product property.

## Image contract

Each SKU has one non-interlaced 8-bit RGBA 512 × 512 synthetic PNG. Packaging contains no real
brand, trademark, price, barcode, or required readable label. The dataset records exact prompt
provenance. Images may be regenerated only as a new dataset revision because their checksums are
part of this version.

## Floor-map contract

`scripts/render_synthetic_floor_map.py` projects authored coordinates into a top-down view. Positive
x remains rightward; positive y points toward the rear and is inverted on screen so the rear appears
at the top. The renderer ignores z for position and draws exact x/y stacks from lowest to highest z,
using item identifier as the stable equal-z tie-breaker. It does not cluster nearby items or draw
package footprints because the dataset defines no package-rotation convention.

The committed `floor-map.svg` is a scalable static view. `floor-map.html` embeds the same SVG and
adds local product-image and metadata selection. Fixtures are drawn from 3D bounds projected to x/y;
entrance and circulation context comes from 2D layout polygons. Rendering is deterministic and
independent of inventory-array order. Tests require the committed artifacts to equal fresh renderer
output byte for byte.

### Floor-map theory note

```text
Theory:      The map is a projection of authored ground truth: meters determine geometry and z only
             determines visibility order; the renderer never infers a more plausible store.
Instead of:  Image generation or hand-edited drawing, which could silently move inventory.
Reused:      Dataset validation plus Python JSON/HTML/XML-compatible text generation.
New concept: Deterministic floor projection: manifest geometry -> static SVG -> interactive HTML.
Assumes:     Axis-aligned fixture bounds, simple layout polygons, and exact x/y stack identity.
Cost:        O(n log n) item ordering and two small derived files; no runtime dependencies.
Watch:       Clearances are synthetic planning dimensions, not an accessibility-code certification.
```

## Verification

`scripts/validate_synthetic_inventory.py` rejects invalid identity, geometry, numeric fields, dates,
unsafe paths, invalid layout polygons, missing or extra PNG files, wrong PNG dimensions, and checksum
changes. The focused tests cover the committed dataset plus out-of-bounds geometry, expiry order,
duplicate identifiers, path traversal, checksum tampering, projection, stacking, escaping, and exact
map regeneration.

## Theory note

```text
Theory:      This is one immutable SKU-lot snapshot whose authored fixture-local coordinates and
             image hashes are ground truth for tests, not measurements recovered from a camera.
Instead of:  Runtime inventory integration or per-unit rows; both need different contracts.
Reused:      The repository's evals boundary and Python JSON, date, path, hash, and struct libraries.
New concept: Synthetic inventory snapshot: manifest + SKU lots + content-addressed product images.
Assumes:     A trusted local checkout, axis-aligned fixtures, and one catalog image per SKU lot.
Cost:        Validation is linear in records and reads every image once to hash about 9 MB total.
Watch:       Centroids are bounded, but package overlap and physical shelf support are not modeled.
```

A second modeled store belongs in a separate dataset directory with its own manifest and fixtures.
Per-unit tracking or live stock updates require a new schema version, not special fields in v1.

Run:

```bash
python3 scripts/validate_synthetic_inventory.py
python3 -m scripts.render_synthetic_floor_map
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_synthetic_inventory.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_synthetic_floor_map.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
