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
- The modeled store is 11 m wide, 13 m deep, and 3 m high.
- The origin is the front-left floor corner. Positive x moves toward the right wall, positive y
  moves from checkout to the rear coolers, and positive z moves upward.
- `position_m` is the package centroid as a three-number array in meters.
- Every position names a fixture and zone and falls inside that fixture's axis-aligned bounds.
- `facing_vector` is nonzero. `shelf_level` is a positive, fixture-local level number.

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

Each SKU has one non-interlaced 8-bit RGBA 512 × 512 synthetic PNG. Packaging contains no real brand, trademark, price,
barcode, or required readable label. The dataset records exact prompt provenance. Images may be
regenerated only as a new dataset revision because their checksums are part of this version.

## Verification

`scripts/validate_synthetic_inventory.py` rejects invalid identity, geometry, numeric fields, dates,
unsafe paths, missing or extra PNG files, wrong PNG dimensions, and checksum changes. The focused
tests cover the committed dataset plus out-of-bounds geometry, expiry order, duplicate identifiers,
path traversal, and checksum tampering.

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
PYTHONPATH=src python3 -m unittest discover -s tests -p 'test_synthetic_inventory.py' -v
PYTHONPATH=src python3 -m unittest discover -s tests -v
```
