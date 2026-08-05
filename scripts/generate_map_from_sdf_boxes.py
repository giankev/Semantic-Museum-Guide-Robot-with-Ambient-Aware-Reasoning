#!/usr/bin/env python3
"""Generate the deterministic supplied-museum proxy map and audit overlay."""

from __future__ import annotations

import argparse
import importlib.util
import json
import math
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw


REPO_ROOT = Path(__file__).resolve().parents[1]
WORLD = REPO_ROOT / "exchange/museum_ws/src/museum_assistant/worlds/supplied_museum/museum_nav.world"
MAP_DIR = REPO_ROOT / "exchange/museum_ws/src/museum_assistant/maps"
AUDIT_DIR = REPO_ROOT / ".museum_layout_audit"
CROP = {"x_min": -8.0, "x_max": 42.0, "y_min": -8.0, "y_max": 22.0}
RESOLUTION = 0.05
PREFIXES = ("nav_boundary_", "nav_wall_", "nav_obstacle_")
LANDMARK_PREFIX = "nav_obstacle_landmark_"
EAST_ROUTE = {"start": [0.0, 0.0], "goal": [24.0, 0.0]}
GROUNDED_LANDMARKS = {
    "nav_obstacle_landmark_upper_panel": {
        "source_bounds": [10.607, 16.928, 8.850, 9.050],
        "source_feature": "long upper exhibition panel",
    },
    "nav_obstacle_landmark_upper_column": {
        "source_bounds": [19.928, 21.042, 2.462, 3.576],
        "source_feature": "upper asymmetric freestanding panel/column",
    },
    "nav_obstacle_landmark_lower_column": {
        "source_bounds": [19.600, 20.812, -5.129, -3.917],
        "source_feature": "lower asymmetric freestanding panel/column",
    },
}
CANDIDATES = {
    "candidate_start": {"x": 0.0, "y": 0.0, "yaw": 0.0},
    "candidate_north": {"x": 0.0, "y": 16.0, "yaw": 1.5708},
    "candidate_east": {"x": 30.0, "y": 0.0, "yaw": 0.0},
}


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
                rotations = model_pose[3:] + link_pose[3:] + collision_pose[3:]
                if any(abs(value) > 1e-9 for value in rotations):
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


def rasterize(boxes):
    width, height = map_dimensions()
    cells = bytearray([254]) * (width * height)
    for box in boxes:
        x0, x1 = box["x"] - box["size_x"]/2, box["x"] + box["size_x"]/2
        y0, y1 = box["y"] - box["size_y"]/2, box["y"] + box["size_y"]/2
        col0 = max(0, math.floor((x0 - CROP["x_min"]) / RESOLUTION))
        col1 = min(width - 1, math.ceil((x1 - CROP["x_min"]) / RESOLUTION) - 1)
        bottom0 = max(0, math.floor((y0 - CROP["y_min"]) / RESOLUTION))
        bottom1 = min(height - 1, math.ceil((y1 - CROP["y_min"]) / RESOLUTION) - 1)
        for bottom_row in range(bottom0, bottom1 + 1):
            image_row = height - 1 - bottom_row
            start = image_row*width + col0
            cells[start:start + col1-col0+1] = bytes([0]) * (col1-col0+1)
    return width, height, cells


def write_pgm(path, width, height, cells):
    header = f"P5\n# deterministic museum_nav.world box raster\n{width} {height}\n255\n".encode("ascii")
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


def clearance_from_map(point, width, height, cells):
    best = float("inf")
    for row in range(height):
        y = CROP["y_max"] - (row + 0.5)*RESOLUTION
        for column in range(width):
            if cells[row*width + column] != 0:
                continue
            x = CROP["x_min"] + (column + 0.5)*RESOLUTION
            dx = max(abs(point["x"] - x) - RESOLUTION/2, 0.0)
            dy = max(abs(point["y"] - y) - RESOLUTION/2, 0.0)
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
        raise RuntimeError("Cannot load the accepted layout exporter")
    spec.loader.exec_module(module)
    module.COLLISION_DAE = WORLD.parent / "model.dae"
    triangles, _, _, _ = module.load_world_geometry()
    return module.section_polygons(triangles)


def east_route_clearance(boxes):
    """Minimum point clearance from the x=0..24, y=0 route to a proxy box."""
    start_x, end_x = EAST_ROUTE["start"][0], EAST_ROUTE["goal"][0]
    best = float("inf")
    nearest = None
    for box in boxes:
        left, right = box["x"] - box["size_x"]/2, box["x"] + box["size_x"]/2
        bottom, top = box["y"] - box["size_y"]/2, box["y"] + box["size_y"]/2
        dx = max(left - end_x, start_x - right, 0.0)
        dy = max(bottom, -top, 0.0)
        clearance = math.hypot(dx, dy)
        if clearance < best:
            best, nearest = clearance, box["name"]
    return round(best, 3), nearest


def render_overlay(path, polygons, boxes, markers):
    scale = 28
    width = round((CROP["x_max"] - CROP["x_min"])*scale)
    height = round((CROP["y_max"] - CROP["y_min"])*scale)
    header = 82
    image = Image.new("RGB", (width, height + header), "white")
    draw = ImageDraw.Draw(image, "RGBA")
    def pixel(x, y):
        return ((x-CROP["x_min"])*scale, header + (CROP["y_max"]-y)*scale)
    for x in range(-5, 43, 5):
        px, _ = pixel(x, 0)
        draw.line((px, header, px, header+height), fill=(190, 205, 215, 255), width=1)
        draw.text((px+2, header+height-14), str(x), fill=(70, 85, 95, 255))
    for y in range(-5, 23, 5):
        _, py = pixel(0, y)
        draw.line((0, py, width, py), fill=(190, 205, 215, 255), width=1)
        draw.text((2, py-13), str(y), fill=(70, 85, 95, 255))
    for polygon in polygons:
        points = [pixel(x, y) for x, y in polygon]
        if len(points) >= 3:
            draw.polygon(points, fill=(69, 90, 100, 75))
        draw.line(points + [points[0]], fill=(55, 71, 79, 130), width=1)
    for box in boxes:
        first = pixel(box["x"]-box["size_x"]/2, box["y"]+box["size_y"]/2)
        second = pixel(box["x"]+box["size_x"]/2, box["y"]-box["size_y"]/2)
        draw.rectangle((first[0], first[1], second[0], second[1]),
                       fill=(229, 57, 53, 105), outline=(183, 28, 28, 255), width=2)
    colours = {"candidate_start": (255, 111, 0, 255), "candidate_north": (0, 137, 123, 255),
               "candidate_east": (94, 53, 177, 255), "visitor_marker": (21, 101, 192, 255),
               "guide_marker": (46, 125, 50, 255), "staff_marker": (106, 27, 154, 255)}
    for name, point in {**markers, **CANDIDATES}.items():
        px, py = pixel(point["x"], point["y"])
        draw.ellipse((px-7, py-7, px+7, py+7), fill=colours[name], outline="white", width=2)
        draw.text((px+9, py-8), name, fill=colours[name])
    draw.rectangle((0, header, width-1, header+height-1), outline=(239, 108, 0, 255), width=4)
    draw.text((12, 10), "Supplied museum deterministic navigation proxy", fill=(23, 37, 42, 255))
    draw.text((12, 32), "Gray: original z=0.15..1.20 m geometry  |  Red: proxy collision boxes", fill=(69, 90, 100, 255))
    draw.text((12, 54), "Crop x=-8..42 m, y=-8..22 m  |  5 m grid", fill=(69, 90, 100, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)


def render_east_landmarks_overlay(path, polygons, boxes):
    scale = 42
    x_min, x_max, y_min, y_max = -1.0, 25.0, -7.0, 11.0
    width = round((x_max-x_min)*scale)
    height = round((y_max-y_min)*scale)
    header = 92
    image = Image.new("RGB", (width, height+header), "white")
    draw = ImageDraw.Draw(image, "RGBA")

    def pixel(x, y):
        return ((x-x_min)*scale, header+(y_max-y)*scale)

    for x in range(0, 26):
        px, _ = pixel(x, 0)
        draw.line((px, header, px, header+height), fill=(218, 226, 231, 255), width=1)
        if x % 5 == 0:
            draw.text((px+2, header+height-14), str(x), fill=(70, 85, 95, 255))
    for y in range(-7, 12):
        _, py = pixel(0, y)
        draw.line((0, py, width, py), fill=(218, 226, 231, 255), width=1)
        if y % 5 == 0:
            draw.text((2, py-13), str(y), fill=(70, 85, 95, 255))
    for polygon in polygons:
        points = [pixel(x, y) for x, y in polygon]
        if len(points) >= 3:
            draw.polygon(points, fill=(69, 90, 100, 55))
        draw.line(points+[points[0]], fill=(55, 71, 79, 100), width=1)
    for box in boxes:
        first = pixel(box["x"]-box["size_x"]/2, box["y"]+box["size_y"]/2)
        second = pixel(box["x"]+box["size_x"]/2, box["y"]-box["size_y"]/2)
        landmark = box["name"].startswith(LANDMARK_PREFIX)
        fill = (255, 152, 0, 150) if landmark else (211, 47, 47, 80)
        outline = (239, 108, 0, 255) if landmark else (183, 28, 28, 220)
        draw.rectangle((first[0], first[1], second[0], second[1]),
                       fill=fill, outline=outline, width=3 if landmark else 2)
        if landmark:
            number = list(GROUNDED_LANDMARKS).index(box["name"])+1
            draw.text((first[0]+5, first[1]+4), str(number), fill=(121, 50, 0, 255))
    # Guaranteed usable center band and intended route.
    band_top = pixel(0, 1.5)[1]
    band_bottom = pixel(0, -1.5)[1]
    route_left, route_right = pixel(0, 0)[0], pixel(24, 0)[0]
    draw.rectangle((route_left, band_top, route_right, band_bottom),
                   fill=(0, 121, 107, 35), outline=(0, 121, 107, 180), width=2)
    start = pixel(0, 0); goal = pixel(24, 0)
    draw.line((start[0], start[1], goal[0], goal[1]), fill=(21, 101, 192, 255), width=5)
    draw.ellipse((start[0]-7, start[1]-7, start[0]+7, start[1]+7), fill=(255, 111, 0, 255))
    draw.ellipse((goal[0]-7, goal[1]-7, goal[0]+7, goal[1]+7), fill=(94, 53, 177, 255))
    draw.text((start[0]+10, start[1]-18), "start (0,0)", fill=(255, 111, 0, 255))
    draw.text((goal[0]-105, goal[1]+10), "east goal (24,0)", fill=(94, 53, 177, 255))
    opening_x = pixel(22, 0)[0]
    opening_top, opening_bottom = pixel(22, 3)[1], pixel(22, -3)[1]
    draw.line((opening_x, opening_top, opening_x, opening_bottom), fill=(0, 188, 212, 255), width=6)
    draw.text((opening_x+7, opening_top+4), "x=22 opening: 6.0 m", fill=(0, 96, 100, 255))
    clearance, nearest = east_route_clearance(boxes)
    draw.text((12, 10), "East route: three grounded asymmetric laser landmarks", fill=(23, 37, 42, 255))
    draw.text((12, 34), "Gray: original model.dae  |  Red: existing proxy  |  Orange: landmarks 1..3",
              fill=(69, 90, 100, 255))
    draw.text((12, 58), f"Route clearance: {clearance:.2f} m (nearest {nearest})  |  1 m grid",
              fill=(0, 105, 92, 255))
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "PNG", optimize=True)


def build_report(boxes, width, height, cells, markers):
    by_name = {box["name"]: box for box in boxes}
    north_west = by_name["nav_wall_central_north_west"]
    north_east = by_name["nav_wall_central_north_east"]
    east_south = by_name["nav_wall_central_east_south"]
    east_north = by_name["nav_wall_central_east_north"]
    north_opening = (
        north_east["x"] - north_east["size_x"]/2
        - (north_west["x"] + north_west["size_x"]/2)
    )
    east_opening = (
        east_north["y"] - east_north["size_y"]/2
        - (east_south["y"] + east_south["size_y"]/2)
    )
    route_clearance, nearest_route_box = east_route_clearance(boxes)
    candidates = {}
    for name, point in CANDIDATES.items():
        column, row = world_to_cell(point["x"], point["y"], width, height)
        candidates[name] = {**point, "map_cell": [column, row],
                            "free": cells[row*width + column] == 254,
                            "clearance_m": clearance_from_map(point, width, height, cells)}
    return {
        "schema_version": 1,
        "source_world": str(WORLD.relative_to(REPO_ROOT)),
        "number_of_navigation_boxes": len(boxes),
        "navigation_box_limit": 35,
        "number_of_grounded_landmarks": len(
            [box for box in boxes if box["name"].startswith(LANDMARK_PREFIX)]
        ),
        "grounded_landmarks": GROUNDED_LANDMARKS,
        "navigation_boxes": boxes,
        "crop_bounds_world_m": CROP,
        "occupancy_map": {"width_cells": width, "height_cells": height,
                          "resolution_m_per_cell": RESOLUTION,
                          "origin": [CROP["x_min"], CROP["y_min"], 0.0],
                          "image_row_zero_world_y": CROP["y_max"],
                          "occupied_value": 0, "free_value": 254},
        "candidate_poses": candidates,
        "marker_positions": markers,
        "openings": {
            "central_to_north": {"width_m": round(north_opening, 3), "line": "y=10", "interval": [-3.0, 3.0]},
            "central_to_east": {"width_m": round(east_opening, 3), "line": "x=22", "interval": [-3.0, 3.0]},
        },
        "east_route": {
            **EAST_ROUTE,
            "minimum_clearance_m": route_clearance,
            "nearest_proxy_box": nearest_route_box,
            "required_minimum_clearance_m": 1.5,
        },
        "intentionally_omitted_visible_geometry": [
            "repetitive side-room partitions and decorative recesses",
            "most artwork panels and frames beyond the three grounded landmarks",
            "most small columns, window details, and trim",
            "all original geometry outside the bounded collision crop",
        ],
        "possible_visual_collision_disagreements": [
            "Proxy separators are axis-aligned and simplify curved or angled transitions near the east connection.",
            "The complete visual mesh remains visible outside the closed proxy boundary but has no collision there.",
            "Visible internal walls and small obstacles beyond the three landmarks remain intentionally non-colliding.",
            "The two retained central obstacles approximate large visible panels with boxes.",
        ],
    }


def generate(world_path=WORLD, map_dir=MAP_DIR, audit_dir=AUDIT_DIR):
    boxes = load_boxes(world_path)
    width, height, cells = rasterize(boxes)
    map_dir.mkdir(parents=True, exist_ok=True)
    audit_dir.mkdir(parents=True, exist_ok=True)
    write_pgm(map_dir / "supplied_museum_nav.pgm", width, height, cells)
    write_yaml(map_dir / "supplied_museum_nav.yaml")
    markers = marker_positions(world_path)
    polygons = original_section_polygons()
    render_overlay(audit_dir / "nav_proxy_overlay.png", polygons, boxes, markers)
    render_east_landmarks_overlay(
        audit_dir / "east_landmarks_overlay.png", polygons, boxes
    )
    report = build_report(boxes, width, height, cells, markers)
    (audit_dir / "nav_proxy_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--world", type=Path, default=WORLD)
    args = parser.parse_args()
    report = generate(args.world)
    occupancy = report["occupancy_map"]
    print(f"Generated {MAP_DIR / 'supplied_museum_nav.pgm'}")
    print(f"Generated {MAP_DIR / 'supplied_museum_nav.yaml'}")
    print(f"Generated {AUDIT_DIR / 'nav_proxy_overlay.png'}")
    print(f"Generated {AUDIT_DIR / 'nav_proxy_report.json'}")
    print(f"Generated {AUDIT_DIR / 'east_landmarks_overlay.png'}")
    print(f"{report['number_of_navigation_boxes']} boxes; {occupancy['width_cells']}x{occupancy['height_cells']} cells")


if __name__ == "__main__":
    main()
