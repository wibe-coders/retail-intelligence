#!/usr/bin/env python3
"""Render the synthetic inventory as deterministic top-down SVG and HTML maps."""

from __future__ import annotations

import argparse
import html
import json
import math
from pathlib import Path
from typing import Any

from scripts.validate_synthetic_inventory import (
    DEFAULT_DATASET_DIRECTORY,
    load_dataset,
    validate_documents,
)


CANVAS_WIDTH = 1000
CANVAS_HEIGHT = 865
MAP_ORIGIN_X = 70
MAP_ORIGIN_Y = 70
PIXELS_PER_METER = 55
LEGEND_X = 520

CATEGORY_COLORS = {
    "chilled-drink": "#1677ff",
    "packaged-snack": "#f59e0b",
    "confectionery": "#db2777",
    "checkout-impulse": "#8b5cf6",
    "fresh-food": "#16a34a",
    "fresh-produce": "#65a30d",
    "fresh-bakery": "#b45309",
    "health": "#dc2626",
    "travel-needs": "#0891b2",
    "electronics-accessory": "#475569",
    "household": "#7c3aed",
}

ZONE_COLORS = {
    "refrigerated": "#dbeafe",
    "center-dry-goods": "#fef3c7",
    "checkout-impulse": "#ede9fe",
    "fresh-grab-and-go": "#dcfce7",
    "health-household": "#e0f2fe",
}

FIXTURE_LABELS = {
    "left-cold": "Left coolers",
    "rear-cold": "Rear coolers",
    "gondola-a": "Gondola A",
    "gondola-b": "Gondola B",
    "checkout-rack": "Checkout",
    "fresh-front": "Fresh food",
}

FEATURE_LABELS = {
    "entrance": "Entrance",
    "front-circulation": "",
}


def project_position(
    position_m: list[float], store_depth_m: float
) -> tuple[float, float]:
    """Project authored x/y meters while placing the rear of the store at the top."""

    x_m, y_m, _z_m = position_m
    return (
        MAP_ORIGIN_X + x_m * PIXELS_PER_METER,
        MAP_ORIGIN_Y + (store_depth_m - y_m) * PIXELS_PER_METER,
    )


def projected_rectangle(
    bounds_m: list[list[float]], store_depth_m: float
) -> tuple[float, float, float, float]:
    """Project an axis-aligned 3D fixture bound into an SVG rectangle."""

    minimum, maximum = bounds_m
    left, bottom = project_position(minimum, store_depth_m)
    right, top = project_position(maximum, store_depth_m)
    return left, top, right - left, bottom - top


def render_svg(manifest: dict[str, Any], inventory: dict[str, Any]) -> str:
    """Return a deterministic top-down SVG for validated dataset documents."""

    store_width, store_depth, _store_height = manifest["coordinate_system"][
        "store_bounds_m"
    ]
    map_width = store_width * PIXELS_PER_METER
    map_height = store_depth * PIXELS_PER_METER
    ordered_items = sorted(inventory["items"], key=lambda item: item["item_id"])
    numbered_items = {
        item["item_id"]: number
        for number, item in enumerate(ordered_items, start=1)
    }

    parts = [_svg_header(manifest["title"]), _svg_styles()]
    parts.extend(_render_grid(store_width, store_depth))
    parts.extend(_render_layout_features(manifest["layout_features"], store_depth))
    parts.extend(_render_fixtures(manifest["fixtures"], store_depth))
    parts.extend(_render_items(ordered_items, numbered_items, store_depth))
    parts.extend(_render_legend(ordered_items, numbered_items))
    parts.extend(
        [
            f'<rect class="store-outline" x="{MAP_ORIGIN_X}" y="{MAP_ORIGIN_Y}" '
            f'width="{map_width}" height="{map_height}"/>',
            f'<text class="orientation" x="{MAP_ORIGIN_X + map_width / 2}" y="40">'
            "REAR OF STORE</text>",
            f'<text class="orientation" x="{MAP_ORIGIN_X + map_width / 2}" '
            f'y="{MAP_ORIGIN_Y + map_height + 35}">FRONT / CHECKOUT</text>',
            "</svg>",
        ]
    )
    return "\n".join(parts) + "\n"


def render_html(
    manifest: dict[str, Any], inventory: dict[str, Any], svg: str
) -> str:
    """Wrap a rendered map in an interactive, self-contained HTML viewer."""

    ordered_items = sorted(inventory["items"], key=lambda item: item["item_id"])
    item_json = json.dumps(ordered_items, ensure_ascii=False).replace("</", "<\\/")
    title = html.escape(manifest["title"])
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title} — Top-down floor map</title>
  <style>
    :root {{ color-scheme: light; font-family: Inter, ui-sans-serif, system-ui, sans-serif; }}
    body {{ margin: 0; background: #f8fafc; color: #0f172a; }}
    main {{ display: grid; grid-template-columns: minmax(0, 1fr) 300px; min-height: 100vh; }}
    .map {{ padding: 20px; overflow: auto; }}
    .map svg {{ display: block; width: 100%; min-width: 760px; height: auto; background: white;
      border: 1px solid #cbd5e1; border-radius: 12px; box-shadow: 0 8px 24px #0f172a12; }}
    aside {{ padding: 24px; background: white; border-left: 1px solid #e2e8f0; }}
    aside img {{ width: 100%; aspect-ratio: 1; object-fit: contain; border-radius: 10px;
      background: #f1f5f9; }}
    h1 {{ margin: 0 0 4px; font-size: 20px; }}
    h2 {{ margin: 18px 0 4px; font-size: 17px; }}
    p {{ margin: 4px 0; line-height: 1.45; }}
    .muted {{ color: #64748b; font-size: 13px; }}
    .inventory-marker {{ cursor: pointer; }}
    .inventory-marker:focus .marker-dot, .inventory-marker:hover .marker-dot {{
      stroke: #0f172a; stroke-width: 3; filter: drop-shadow(0 2px 3px #0004); }}
    @media (max-width: 900px) {{ main {{ grid-template-columns: 1fr; }} aside {{ border: 0;
      border-top: 1px solid #e2e8f0; }} }}
  </style>
</head>
<body>
<main>
  <section class="map" aria-label="Top-down store map">
{svg}
  </section>
  <aside aria-live="polite">
    <h1>Inventory details</h1>
    <p class="muted">Select a numbered marker. Items at the same x/y coordinate are drawn from
      lowest to highest z, so the highest item remains visible.</p>
    <img id="product-image" alt="Selected synthetic product">
    <h2 id="product-name">Select an item</h2>
    <p id="product-brand" class="muted"></p>
    <p id="product-price"></p>
    <p id="product-location"></p>
    <p id="product-dates" class="muted"></p>
  </aside>
</main>
<script>
  const items = {item_json};
  const byId = new Map(items.map(item => [item.item_id, item]));
  function selectItem(itemId) {{
    const item = byId.get(itemId);
    if (!item) return;
    document.getElementById("product-image").src = item.image.path;
    document.getElementById("product-image").alt = item.name;
    document.getElementById("product-name").textContent = item.name;
    document.getElementById("product-brand").textContent =
      `${{item.synthetic_brand}} · ${{item.category}} · ${{item.sku}}`;
    document.getElementById("product-price").textContent =
      `$${{(item.price_cents / 100).toFixed(2)}} · ${{item.quantity_on_hand}} on hand`;
    document.getElementById("product-location").textContent =
      `${{item.fixture_id}}, shelf ${{item.shelf_level}} · ` +
      `[${{item.position_m.map(value => value.toFixed(3)).join(", ")}}] m`;
    document.getElementById("product-dates").textContent =
      `Placed ${{item.placed_at}} · Date marking ${{item.expires_on ?? "none"}}`;
  }}
  document.querySelectorAll(".inventory-marker").forEach(marker => {{
    marker.addEventListener("click", event => {{ event.preventDefault(); selectItem(marker.dataset.itemId); }});
    marker.addEventListener("keydown", event => {{
      if (event.key === "Enter" || event.key === " ") {{ event.preventDefault(); selectItem(marker.dataset.itemId); }}
    }});
  }});
  if (items.length) selectItem(items[0].item_id);
</script>
</body>
</html>
"""


def generate_floor_maps(
    dataset_directory: Path,
    svg_path: Path | None = None,
    html_path: Path | None = None,
) -> tuple[Path, Path]:
    """Validate a dataset and write its SVG and interactive HTML maps."""

    manifest, inventory = load_dataset(dataset_directory)
    errors = validate_documents(manifest, inventory, dataset_directory)
    if errors:
        raise ValueError("dataset validation failed:\n" + "\n".join(errors))
    svg = render_svg(manifest, inventory)
    rendered_svg = svg_path or dataset_directory / "floor-map.svg"
    rendered_html = html_path or dataset_directory / "floor-map.html"
    rendered_svg.write_text(svg, encoding="utf-8")
    rendered_html.write_text(render_html(manifest, inventory, svg), encoding="utf-8")
    return rendered_svg, rendered_html


def _svg_header(title: str) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_WIDTH}" '
        f'height="{CANVAS_HEIGHT}" viewBox="0 0 {CANVAS_WIDTH} {CANVAS_HEIGHT}" '
        f'role="img" aria-labelledby="map-title map-description">\n'
        f'<title id="map-title">{html.escape(title)} top-down floor map</title>\n'
        '<desc id="map-description">Fixtures are drawn to scale from authored bounds. '
        'Numbered inventory markers use x and y position; z controls drawing order.</desc>'
    )


def _svg_styles() -> str:
    return """<defs>
  <pattern id="entrance-stripes" width="10" height="10" patternUnits="userSpaceOnUse"
    patternTransform="rotate(45)"><rect width="5" height="10" fill="#bbf7d0"/></pattern>
</defs>
<style>
  .store-floor { fill: #f8fafc; }
  .store-outline { fill: none; stroke: #0f172a; stroke-width: 4; }
  .grid-line { stroke: #cbd5e1; stroke-width: 1; stroke-dasharray: 2 5; }
  .grid-label { fill: #64748b; font: 10px ui-sans-serif, system-ui, sans-serif; }
  .fixture { stroke: #475569; stroke-width: 1.5; }
  .fixture-label { fill: #334155; font: 10px ui-sans-serif, system-ui, sans-serif;
    text-anchor: middle; dominant-baseline: middle; pointer-events: none; }
  .feature { stroke-width: 2; }
  .feature-label { fill: #475569; font: 10px ui-sans-serif, system-ui, sans-serif;
    text-anchor: middle; dominant-baseline: middle; }
  .marker-dot { stroke: white; stroke-width: 2; }
  .marker-number { fill: white; font: bold 9px ui-sans-serif, system-ui, sans-serif;
    text-anchor: middle; dominant-baseline: middle; pointer-events: none; }
  .legend-heading { fill: #0f172a; font: bold 15px ui-sans-serif, system-ui, sans-serif; }
  .legend-text { fill: #334155; font: 11px ui-sans-serif, system-ui, sans-serif; }
  .orientation { fill: #334155; font: bold 12px ui-sans-serif, system-ui, sans-serif;
    text-anchor: middle; letter-spacing: 1px; }
</style>"""


def _render_grid(store_width: float, store_depth: float) -> list[str]:
    width = store_width * PIXELS_PER_METER
    height = store_depth * PIXELS_PER_METER
    parts = [
        f'<rect class="store-floor" x="{MAP_ORIGIN_X}" y="{MAP_ORIGIN_Y}" '
        f'width="{width}" height="{height}"/>'
    ]
    for meter in range(math.floor(store_width) + 1):
        x = MAP_ORIGIN_X + meter * PIXELS_PER_METER
        parts.append(
            f'<line class="grid-line" x1="{x}" y1="{MAP_ORIGIN_Y}" x2="{x}" '
            f'y2="{MAP_ORIGIN_Y + height}"/>'
        )
        parts.append(
            f'<text class="grid-label" x="{x + 3}" y="{MAP_ORIGIN_Y + height - 5}">'
            f"x={meter}</text>"
        )
    for meter in range(math.floor(store_depth) + 1):
        y = MAP_ORIGIN_Y + (store_depth - meter) * PIXELS_PER_METER
        parts.append(
            f'<line class="grid-line" x1="{MAP_ORIGIN_X}" y1="{y}" '
            f'x2="{MAP_ORIGIN_X + width}" y2="{y}"/>'
        )
        parts.append(
            f'<text class="grid-label" x="{MAP_ORIGIN_X + 3}" y="{y - 3}">y={meter}</text>'
        )
    return parts


def _render_layout_features(
    features: list[dict[str, Any]], store_depth: float
) -> list[str]:
    parts: list[str] = []
    for feature in features:
        projected = [project_position([x, y, 0.0], store_depth) for x, y in feature["footprint_m"]]
        points = " ".join(f"{x},{y}" for x, y in projected)
        label_x = sum(point[0] for point in projected) / len(projected)
        label_y = sum(point[1] for point in projected) / len(projected)
        label = FEATURE_LABELS.get(feature["feature_id"], feature["name"])
        if feature["feature_type"] == "entrance":
            fill, stroke, dash = "url(#entrance-stripes)", "#16a34a", ""
        else:
            fill, stroke, dash = "#f1f5f9", "#94a3b8", ' stroke-dasharray="8 6"'
        parts.append(
            f'<g data-feature-id="{html.escape(feature["feature_id"], quote=True)}">'
            f'<title>{html.escape(feature["name"])}</title>'
            f'<polygon class="feature" points="{points}" fill="{fill}" stroke="{stroke}"{dash}/>'
            f'<text class="feature-label" x="{label_x}" y="{label_y}">'
            f'{html.escape(label)}</text></g>'
        )
    return parts


def _render_fixtures(fixtures: list[dict[str, Any]], store_depth: float) -> list[str]:
    parts: list[str] = []
    for fixture in fixtures:
        x, y, width, height = projected_rectangle(fixture["bounds_m"], store_depth)
        fill = ZONE_COLORS.get(fixture["zone_id"], "#e2e8f0")
        label = FIXTURE_LABELS.get(fixture["fixture_id"], fixture["fixture_id"])
        label_x = x + width / 2
        label_y = y + height / 2
        transform = (
            f' transform="rotate(-90 {label_x} {label_y})"'
            if width < 85 and height > 120
            else ""
        )
        parts.append(
            f'<g data-fixture-id="{html.escape(fixture["fixture_id"], quote=True)}">'
            f'<title>{html.escape(fixture["name"])}</title>'
            f'<rect class="fixture" x="{x}" y="{y}" width="{width}" height="{height}" '
            f'fill="{fill}" rx="3"/>'
            f'<text class="fixture-label" x="{label_x}" y="{label_y}"{transform}>'
            f'{html.escape(label)}</text></g>'
        )
    return parts


def _render_items(
    items: list[dict[str, Any]], numbered_items: dict[str, int], store_depth: float
) -> list[str]:
    parts: list[str] = []
    for item in sorted(items, key=lambda value: (value["position_m"][2], value["item_id"])):
        x, y = project_position(item["position_m"], store_depth)
        number = numbered_items[item["item_id"]]
        color = CATEGORY_COLORS.get(item["category"], "#334155")
        title = html.escape(
            f'{number}. {item["name"]} — {item["sku"]} — '
            f'[{", ".join(str(value) for value in item["position_m"])}] m'
        )
        parts.append(
            f'<a href="{html.escape(item["image"]["path"], quote=True)}" target="_blank">'
            f'<g class="inventory-marker" tabindex="0" role="button" '
            f'data-item-id="{html.escape(item["item_id"], quote=True)}" data-z="{item["position_m"][2]}">'
            f'<title>{title}</title><circle class="marker-dot" cx="{x}" cy="{y}" r="10" '
            f'fill="{color}"/><text class="marker-number" x="{x}" y="{y + 0.5}">{number}</text>'
            "</g></a>"
        )
    return parts


def _render_legend(
    items: list[dict[str, Any]], numbered_items: dict[str, int]
) -> list[str]:
    parts = [f'<text class="legend-heading" x="{LEGEND_X}" y="80">Inventory</text>']
    for row, item in enumerate(items):
        y = 104 + row * 28
        number = numbered_items[item["item_id"]]
        color = CATEGORY_COLORS.get(item["category"], "#334155")
        label = item["name"] if len(item["name"]) <= 32 else item["name"][:29] + "…"
        parts.append(
            f'<circle cx="{LEGEND_X + 8}" cy="{y - 4}" r="8" fill="{color}"/>'
            f'<text class="marker-number" x="{LEGEND_X + 8}" y="{y - 3.5}">{number}</text>'
            f'<text class="legend-text" x="{LEGEND_X + 23}" y="{y}">{html.escape(label)}</text>'
        )
    return parts


def main() -> int:
    """Render the configured dataset and report the generated paths."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET_DIRECTORY)
    parser.add_argument("--svg", type=Path)
    parser.add_argument("--html", type=Path)
    arguments = parser.parse_args()
    try:
        svg_path, html_path = generate_floor_maps(
            arguments.dataset.resolve(), arguments.svg, arguments.html
        )
    except (OSError, ValueError) as error:
        print(f"FAIL: {error}")
        return 1
    print(f"WROTE: {svg_path}")
    print(f"WROTE: {html_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
