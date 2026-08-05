#!/usr/bin/env python3
"""Generate the compact supplied-museum proxy map and static audit artifacts."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw
import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "exchange/museum_ws/src/museum_assistant"
WORLD = PACKAGE / "worlds/supplied_museum/museum_nav.world"
ROOM_LAYOUT = PACKAGE / "config/supplied_museum_room_layout.yaml"
MAP_DIR = PACKAGE / "maps"
AUDIT_DIR = REPO_ROOT / ".museum_layout_audit"
RESOLUTION = 0.05
PREFIXES = ("nav_boundary_", "nav_wall_", "nav_obstacle_")
BOX_LIMIT = 40


def load_room_layout(path=ROOM_LAYOUT):
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if data["schema_version"] != 1:
        raise ValueError("Unsupported supplied-museum room-layout schema")
    return data


LAYOUT = load_room_layout()
CROP = {key: float(value) for key, value in LAYOUT["crop"].items()}
CANDIDATES = LAYOUT["candidate_poses"]


def pose_values(element):
    text = element.findtext("pose", default="0 0 0 0 0 0")
    values = [float(value) for value in text.split()]
    if len(values) != 6 or not all(math.isfinite(value) for value in values):
        raise ValueError(f"Invalid pose on {element.tag}: {text!r}")
    return values


def load_boxes(world_path=WORLD):
    root = ET.parse(world_path).getroot()
    boxes = []
    for model in root.findall(".//model"):
        name = model.attrib.get("name", "")
        if not name.startswith(PREFIXES):
            continue
        model_pose = pose_values(model)
        if any(abs(value) > 1e-9 for value in model_pose[3:]):
            raise ValueError(f"Navigation model {name} is not axis-aligned")
        for link in model.findall("link"):
            link_pose = pose_values(link)
            for collision in link.findall("collision"):
                collision_pose = pose_values(collision)
                if any(abs(value) > 1e-9 for value in model_pose[3:] + link_pose[3:] + collision_pose[3:]):
                    raise ValueError(f"Navigation collision {name} is not axis-aligned")
                size_text = collision.findtext("geometry/box/size")
                if size_text is None:
                    raise ValueError(f"Navigation collision {name} is not a box")
                size = [float(value) for value in size_text.split()]
                if len(size) != 3 or not all(math.isfinite(value) and value > 0 for value in size):
                    raise ValueError(f"Invalid box size for {name}: {size_text!r}")
                boxes.append({
                    "name": name,
                    "x": model_pose[0] + link_pose[0] + collision_pose[0],
                    "y": model_pose[1] + link_pose[1] + collision_pose[1],
                    "z": model_pose[2] + link_pose[2] + collision_pose[2],
                    "size_x": size[0], "size_y": size[1], "size_z": size[2],
                })
    return boxes


def map_dimensions():
    return (round((CROP["x_max"] - CROP["x_min"]) / RESOLUTION),
            round((CROP["y_max"] - CROP["y_min"]) / RESOLUTION))


def _cell_center(column, row, height):
    return (CROP["x_min"] + (column + 0.5) * RESOLUTION,
            CROP["y_max"] - (row + 0.5) * RESOLUTION)


def _paint_rectangle(cells, width, height, bounds, value):
    for row in range(height):
        y = CROP["y_max"] - (row + 0.5) * RESOLUTION
        if not bounds["y_min"] <= y <= bounds["y_max"]:
            continue
        col0 = max(0, math.ceil((bounds["x_min"] - CROP["x_min"]) / RESOLUTION - 0.5))
        col1 = min(width - 1, math.floor((bounds["x_max"] - CROP["x_min"]) / RESOLUTION - 0.5))
        if col0 <= col1:
            start = row * width + col0
            cells[start:start + col1 - col0 + 1] = bytes([value]) * (col1 - col0 + 1)


def rasterize(boxes, layout=LAYOUT):
    width, height = map_dimensions()
    cells = bytearray([layout["map"]["unknown_value"]]) * (width * height)
    for area in layout["physical_areas"].values():
        for region in area["validated_free_regions"]:
            if region["type"] != "axis_aligned_rectangle":
                raise ValueError("Only validated axis-aligned regions are supported")
            _paint_rectangle(cells, width, height, region["bounds"], layout["map"]["free_value"])
    for door in layout["doors"].values():
        _paint_rectangle(cells, width, height, door["map_free_region"], layout["map"]["free_value"])
    # Occupancy is deliberately last: collision always overrides validated free space.
    for box in boxes:
        bounds = {
            "x_min": box["x"] - box["size_x"] / 2,
            "x_max": box["x"] + box["size_x"] / 2,
            "y_min": box["y"] - box["size_y"] / 2,
            "y_max": box["y"] + box["size_y"] / 2,
        }
        _paint_rectangle(cells, width, height, bounds, layout["map"]["occupied_value"])
    return width, height, cells


def write_pgm(path, width, height, cells):
    header = f"P5\n# deterministic compact museum proxy\n{width} {height}\n255\n".encode("ascii")
    path.write_bytes(header + bytes(cells))


def write_yaml(path):
    path.write_text(
        "image: supplied_museum_nav.pgm\n"
        f"resolution: {RESOLUTION:.2f}\n"
        f"origin: [{CROP['x_min']:.1f}, {CROP['y_min']:.1f}, 0.0]\n"
        "negate: 0\noccupied_thresh: 0.65\nfree_thresh: 0.196\nmode: trinary\n",
        encoding="utf-8",
    )


def world_to_cell(x, y, width, height):
    column = math.floor((x - CROP["x_min"]) / RESOLUTION)
    bottom_row = math.floor((y - CROP["y_min"]) / RESOLUTION)
    return column, height - 1 - bottom_row


def map_value(x, y, width, height, cells):
    column, row = world_to_cell(x, y, width, height)
    if not 0 <= column < width or not 0 <= row < height:
        return None
    return cells[row * width + column]


def clearance_from_map(point, width, height, cells):
    occupied = LAYOUT["map"]["occupied_value"]
    best = float("inf")
    for row in range(height):
        for column in range(width):
            if cells[row * width + column] != occupied:
                continue
            x, y = _cell_center(column, row, height)
            dx = max(abs(point["x"] - x) - RESOLUTION / 2, 0.0)
            dy = max(abs(point["y"] - y) - RESOLUTION / 2, 0.0)
            best = min(best, math.hypot(dx, dy))
    return round(best, 3)


def marker_positions(world_path=WORLD):
    root = ET.parse(world_path).getroot()
    result = {}
    for name in ("visitor_marker", "guide_marker", "staff_marker"):
        model = root.find(f".//model[@name='{name}']")
        pose = pose_values(model)
        result[name] = {"x": pose[0], "y": pose[1]}
    return result


def original_section_polygons():
    exporter_path = REPO_ROOT / "scripts/export_supplied_museum_topdown.py"
    spec = importlib.util.spec_from_file_location("museum_layout_exporter", exporter_path)
    module = importlib.util.module_from_spec(spec)
    if spec.loader is None:
        raise RuntimeError("Cannot load the layout exporter")
    spec.loader.exec_module(module)
    # The proxy grounding deliberately uses model.dae, never collision.dae.
    module.COLLISION_DAE = WORLD.parent / "model.dae"
    triangles, _, _, _ = module.load_world_geometry()
    return module.section_polygons(triangles)


def _door_map_width(door, width, height, cells):
    raw = float(door["raw_geometric_width"])
    cx, cy = door["center"]
    samples = []
    if door["opening_axis"] == "x":
        count = round(raw / RESOLUTION)
        samples = [(cx - raw / 2 + (i + 0.5) * RESOLUTION, cy) for i in range(count)]
    else:
        count = round(raw / RESOLUTION)
        samples = [(cx, cy - raw / 2 + (i + 0.5) * RESOLUTION) for i in range(count)]
    free = LAYOUT["map"]["free_value"]
    return round(sum(map_value(x, y, width, height, cells) == free for x, y in samples) * RESOLUTION, 3)


def _rect(draw, pixel, bounds, **kwargs):
    a = pixel(bounds["x_min"], bounds["y_max"])
    b = pixel(bounds["x_max"], bounds["y_min"])
    draw.rectangle((a[0], a[1], b[0], b[1]), **kwargs)


def render_overlay(path, polygons, boxes, markers, layout=LAYOUT):
    view = {"x_min": -19.0, "x_max": 43.0, "y_min": -26.0, "y_max": 23.0}
    scale, header = 19, 122
    width = round((view["x_max"] - view["x_min"]) * scale)
    height = round((view["y_max"] - view["y_min"]) * scale)
    image = Image.new("RGB", (width, height + header), "white")
    draw = ImageDraw.Draw(image, "RGBA")

    def pixel(x, y):
        return ((x - view["x_min"]) * scale, header + (view["y_max"] - y) * scale)

    _rect(draw, pixel, CROP, fill=(189, 189, 189, 150), outline=(239, 108, 0, 255), width=3)
    east = layout["experimental_east_area"]["bounds"]
    _rect(draw, pixel, east, fill=(126, 87, 194, 25), outline=(126, 87, 194, 180), width=2)
    for x in range(-15, 44, 5):
        px, _ = pixel(x, 0)
        draw.line((px, header, px, header + height), fill=(207, 216, 220, 180), width=1)
        draw.text((px + 2, header + height - 14), str(x), fill=(55, 71, 79, 255))
    for y in range(-25, 24, 5):
        _, py = pixel(0, y)
        draw.line((0, py, width, py), fill=(207, 216, 220, 180), width=1)
        draw.text((2, py - 13), str(y), fill=(55, 71, 79, 255))
    for polygon in polygons:
        points = [pixel(x, y) for x, y in polygon]
        if len(points) >= 3:
            draw.polygon(points, fill=(55, 71, 79, 38))
        draw.line(points + [points[0]], fill=(38, 50, 56, 90), width=1)
    area_colours = {
        "entrance_area": (255, 193, 7, 100), "central_area": (0, 188, 212, 65),
        "north_gallery": (76, 175, 80, 80), "south_west_gallery": (33, 150, 243, 80),
        "south_east_gallery": (255, 152, 0, 80),
    }
    for name, area in layout["physical_areas"].items():
        for region in area["validated_free_regions"]:
            _rect(draw, pixel, region["bounds"], fill=area_colours[name],
                  outline=area_colours[name][0:3] + (230,), width=2)
        first = area["validated_free_regions"][0]["bounds"]
        draw.text(pixel(first["x_min"] + 0.2, first["y_max"] - 0.25), name,
                  fill=area_colours[name][0:3] + (255,))
    for name, door in layout["doors"].items():
        _rect(draw, pixel, door["map_free_region"], fill=(0, 255, 255, 135),
              outline=(0, 105, 120, 255), width=2)
        draw.text(pixel(door["center"][0] + 0.15, door["center"][1] + 0.15), name,
                  fill=(0, 77, 90, 255))
    for box in boxes:
        bounds = {"x_min": box["x"] - box["size_x"] / 2,
                  "x_max": box["x"] + box["size_x"] / 2,
                  "y_min": box["y"] - box["size_y"] / 2,
                  "y_max": box["y"] + box["size_y"] / 2}
        _rect(draw, pixel, bounds, fill=(211, 47, 47, 120), outline=(183, 28, 28, 255), width=2)
    points = {**markers, **{name: {"x": p["x"], "y": p["y"]} for name, p in CANDIDATES.items()}}
    for name, point in points.items():
        px, py = pixel(point["x"], point["y"])
        colour = (94, 53, 177, 255) if "candidate" in name else (0, 77, 64, 255)
        draw.ellipse((px - 6, py - 6, px + 6, py + 6), fill=colour, outline="white", width=2)
        draw.text((px + 8, py - 8), name, fill=colour)
    draw.text(pixel(23.0, 17.0), "experimental_east_area\ndemo: false\nvalidated: false", fill=(94, 53, 177, 255))
    draw.text((12, 10), "Compact three-gallery supplied-museum navigation proxy", fill=(23, 37, 42, 255))
    draw.text((12, 32), "Gray: unknown  Green/blue/orange: validated free  Red: occupied proxy  Cyan: doors", fill=(55, 71, 79, 255))
    draw.text((12, 54), "Original model.dae geometry shown in charcoal; crop outlined in orange; 5 m grid", fill=(55, 71, 79, 255))
    draw.text((12, 78), "Planned future semantic correspondence only:", fill=(69, 90, 100, 255))
    draw.text((12, 98), "north_gallery -> impressionism_hall | south_west_gallery -> ancient_art_hall | south_east_gallery -> kids_hall",
              fill=(69, 90, 100, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)


def build_report(boxes, width, height, cells, markers, layout=LAYOUT):
    free = layout["map"]["free_value"]
    candidates = {}
    for name, point in CANDIDATES.items():
        candidates[name] = {
            **point,
            "free": map_value(point["x"], point["y"], width, height, cells) == free,
            "clearance_m": clearance_from_map(point, width, height, cells),
            "map_cell": list(world_to_cell(point["x"], point["y"], width, height)),
        }
    allowance = float(layout["clearance_assumptions"]["edge_allowance"])
    doors = {}
    for name, door in layout["doors"].items():
        map_width = _door_map_width(door, width, height, cells)
        doors[name] = {**door, "occupied_map_width": map_width,
                       "usable_width": round(map_width - 2 * allowance, 3)}
    counts = {"occupied": cells.count(layout["map"]["occupied_value"]),
              "free": cells.count(free),
              "unknown": cells.count(layout["map"]["unknown_value"])}
    return {
        "schema_version": 2,
        "source_world": str(WORLD.relative_to(REPO_ROOT)),
        "source_geometry": str((WORLD.parent / "model.dae").relative_to(REPO_ROOT)),
        "crop_bounds_world_m": CROP,
        "physical_room_regions": layout["physical_areas"],
        "candidate_poses": candidates,
        "demo_gallery_candidates": [name for name, point in CANDIDATES.items() if point["demo_gallery"]],
        "doors": doors,
        "topology": layout["topology"],
        "marker_positions": markers,
        "marker_relocation": {"staff_marker": {"from": [35.0, 0.0], "to": [3.5, 4.0],
                                                  "public_adapter_id": "staff_1"}},
        "navigation_boxes": boxes,
        "number_of_navigation_boxes": len(boxes),
        "navigation_box_limit": BOX_LIMIT,
        "occupancy_map": {"width_cells": width, "height_cells": height,
                          "resolution_m_per_cell": RESOLUTION,
                          "origin": [CROP["x_min"], CROP["y_min"], 0.0],
                          "occupied_value": layout["map"]["occupied_value"],
                          "free_value": free, "unknown_value": layout["map"]["unknown_value"],
                          "cell_counts": counts},
        "experimental_east_area": layout["experimental_east_area"],
        "omitted_visible_geometry": [
            "the long east wing outside x=22.2",
            "west-side galleries outside x=-17.5",
            "decorative trim, frames, and repeated small southern posts",
            "unvalidated side compartments inside the crop remain unknown",
        ],
        "visual_proxy_mismatches": [
            "axis-aligned boxes conservatively approximate the curved southern neck",
            "southern gallery zones are separated from the central aisle by validated-map boundaries and panel rows, not full-height room walls",
            "the crop boundary closes visible geometry that continues beyond the compact demo region",
        ],
        "nav2_odometry_topic_audit": {
            "supported_controller_server_parameter": "odom_topic",
            "evidence": "https://docs.nav2.org/configuration/packages/configuring-controller-server.html",
            "resolved_topic": "/museum/ground_truth_odom",
            "explicit_consumers": ["controller_server", "bt_navigator", "velocity_smoother"],
        },
    }


def generate(world_path=WORLD, map_dir=MAP_DIR, audit_dir=AUDIT_DIR):
    boxes = load_boxes(world_path)
    if len(boxes) > BOX_LIMIT:
        raise ValueError(f"Proxy has {len(boxes)} boxes; limit is {BOX_LIMIT}")
    width, height, cells = rasterize(boxes)
    map_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    write_pgm(map_dir / "supplied_museum_nav.pgm", width, height, cells)
    write_yaml(map_dir / "supplied_museum_nav.yaml")
    markers = marker_positions(world_path)
    polygons = original_section_polygons()
    overlay = audit_dir / "multi_room_demo_overlay.png"
    render_overlay(overlay, polygons, boxes, markers)
    # Retain the general proxy artifact names for the existing focused contract.
    render_overlay(audit_dir / "nav_proxy_overlay.png", polygons, boxes, markers)
    report = build_report(boxes, width, height, cells, markers)
    text = json.dumps(report, indent=2, sort_keys=True) + "\n"
    (audit_dir / "multi_room_demo_report.json").write_text(text, encoding="utf-8")
    (audit_dir / "nav_proxy_report.json").write_text(text, encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, default=WORLD)
    args = parser.parse_args()
    report = generate(args.world)
    occupancy = report["occupancy_map"]
    print(f"Generated {MAP_DIR / 'supplied_museum_nav.pgm'}")
    print(f"Generated {MAP_DIR / 'supplied_museum_nav.yaml'}")
    print(f"Generated {AUDIT_DIR / 'multi_room_demo_overlay.png'}")
    print(f"Generated {AUDIT_DIR / 'multi_room_demo_report.json'}")
    print(f"{report['number_of_navigation_boxes']} boxes; {occupancy['width_cells']}x{occupancy['height_cells']} cells")


if __name__ == "__main__":
    main()
