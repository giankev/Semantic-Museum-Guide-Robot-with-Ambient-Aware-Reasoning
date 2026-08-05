#!/usr/bin/env python3
"""Export a static top-down audit of the packaged supplied museum.

This reads COLLADA and SDF/XML only.  It does not import or start ROS, Gazebo,
or Docker.  Pillow is used solely to rasterise the inspected geometry.
"""

from __future__ import annotations

import argparse
import heapq
import json
import math
import re
import time
from collections import deque
from pathlib import Path
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFilter


REPO_ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = (
    REPO_ROOT
    / "exchange/museum_ws/src/museum_assistant/worlds/supplied_museum"
)
COLLISION_DAE = ASSET_DIR / "collision.dae"
WORLD_FILE = ASSET_DIR / "museum.world"
DEFAULT_OUTPUT = REPO_ROOT / ".museum_layout_audit"
SLICE_Z = (0.15, 1.20)
DEMO_CROP = {"x_min": -17.5, "x_max": 22.2, "y_min": -24.5, "y_max": 22.0}
GRID_RESOLUTION = 0.10


def identity():
    return ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0),
            (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))


def matmul(a, b):
    return tuple(tuple(sum(a[r][k] * b[k][c] for k in range(4))
                       for c in range(4)) for r in range(4))


def transform(matrix, point):
    vector = (point[0], point[1], point[2], 1.0)
    result = [sum(matrix[r][c] * vector[c] for c in range(4)) for r in range(4)]
    return tuple(result[:3])


def node_matrix(node, ns):
    result = identity()
    for child in node:
        tag = child.tag.rsplit("}", 1)[-1]
        values = [float(value) for value in (child.text or "").split()]
        if tag == "matrix":
            current = tuple(tuple(values[4 * r + c] for c in range(4))
                            for r in range(4))
        elif tag == "translate":
            current = identity()
            current = tuple(tuple(values[r] if c == 3 and r < 3 else cell
                                  for c, cell in enumerate(row))
                            for r, row in enumerate(current))
        elif tag == "scale":
            current = tuple(tuple(values[r] if r == c and r < 3 else cell
                                  for c, cell in enumerate(row))
                            for r, row in enumerate(identity()))
        elif tag == "rotate":
            x, y, z, degrees = values
            length = math.sqrt(x * x + y * y + z * z)
            x, y, z = x / length, y / length, z / length
            cosine, sine = math.cos(math.radians(degrees)), math.sin(math.radians(degrees))
            one_minus = 1.0 - cosine
            current = (
                (cosine + x*x*one_minus, x*y*one_minus-z*sine, x*z*one_minus+y*sine, 0.0),
                (y*x*one_minus+z*sine, cosine+y*y*one_minus, y*z*one_minus-x*sine, 0.0),
                (z*x*one_minus-y*sine, z*y*one_minus+x*sine, cosine+z*z*one_minus, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        else:
            continue
        result = matmul(result, current)
    return result


def parse_meshes(root, ns):
    meshes = {}
    for geometry in root.findall(".//c:library_geometries/c:geometry", ns):
        mesh = geometry.find("c:mesh", ns)
        if mesh is None:
            continue
        sources = {}
        for source in mesh.findall("c:source", ns):
            array = source.find("c:float_array", ns)
            accessor = source.find("c:technique_common/c:accessor", ns)
            if array is None or accessor is None:
                continue
            values = [float(value) for value in (array.text or "").split()]
            stride = int(accessor.attrib.get("stride", "1"))
            offset = int(accessor.attrib.get("offset", "0"))
            count = int(accessor.attrib["count"])
            sources[source.attrib["id"]] = [
                tuple(values[offset + i*stride:offset + i*stride + stride])
                for i in range(count)
            ]
        vertices = {}
        for element in mesh.findall("c:vertices", ns):
            position = element.find("c:input[@semantic='POSITION']", ns)
            if position is not None:
                vertices[element.attrib["id"]] = position.attrib["source"][1:]
        triangles = []
        position_source = None
        for primitive in list(mesh.findall("c:triangles", ns)) + list(mesh.findall("c:polylist", ns)):
            inputs = primitive.findall("c:input", ns)
            vertex_input = next((item for item in inputs if item.attrib["semantic"] == "VERTEX"), None)
            if vertex_input is None:
                continue
            position_source = vertices[vertex_input.attrib["source"][1:]]
            vertex_offset = int(vertex_input.attrib.get("offset", "0"))
            index_stride = max(int(item.attrib.get("offset", "0")) for item in inputs) + 1
            packed = [int(value) for value in (primitive.findtext("c:p", default="", namespaces=ns)).split()]
            vertex_indices = packed[vertex_offset::index_stride]
            if primitive.tag.endswith("triangles"):
                counts = [3] * int(primitive.attrib["count"])
            else:
                counts = [int(value) for value in primitive.findtext("c:vcount", default="", namespaces=ns).split()]
            cursor = 0
            for count in counts:
                polygon = vertex_indices[cursor:cursor + count]
                cursor += count
                for index in range(1, count - 1):
                    triangles.append((polygon[0], polygon[index], polygon[index + 1]))
        if position_source is not None:
            meshes[geometry.attrib["id"]] = (sources[position_source], triangles)
    return meshes


def load_world_geometry():
    tree = ET.parse(COLLISION_DAE)
    root = tree.getroot()
    namespace = root.tag.split("}", 1)[0][1:]
    ns = {"c": namespace}
    unit = float(root.find("c:asset/c:unit", ns).attrib["meter"])
    up_axis = root.findtext("c:asset/c:up_axis", namespaces=ns)
    if up_axis != "Y_UP":
        raise ValueError(f"Expected Y_UP COLLADA, found {up_axis!r}")
    meshes = parse_meshes(root, ns)
    visual_scene_url = root.find("c:scene/c:instance_visual_scene", ns).attrib["url"][1:]
    scene = root.find(f".//c:visual_scene[@id='{visual_scene_url}']", ns)
    all_triangles = []
    instance_count = 0

    def visit(node, parent):
        nonlocal instance_count
        matrix = matmul(parent, node_matrix(node, ns))
        for instance in node.findall("c:instance_geometry", ns):
            geometry_id = instance.attrib["url"][1:]
            if geometry_id not in meshes:
                continue
            points, triangles = meshes[geometry_id]
            # COLLADA metre scaling followed by the world +90 degree X roll:
            # (dae X, dae Y, dae Z) -> (world x=X, y=-Z, z=Y).
            transformed = []
            for point in points:
                x, y, z = transform(matrix, point)
                transformed.append((unit*x, -unit*z, unit*y))
            all_triangles.extend(tuple(transformed[index] for index in triangle)
                                 for triangle in triangles)
            instance_count += 1
        for child in node.findall("c:node", ns):
            visit(child, matrix)

    for node in scene.findall("c:node", ns):
        visit(node, identity())
    return all_triangles, unit, up_axis, instance_count


def clip_at_z(polygon, threshold, keep_above):
    result = []
    for start, end in zip(polygon, polygon[1:] + polygon[:1]):
        start_inside = start[2] >= threshold if keep_above else start[2] <= threshold
        end_inside = end[2] >= threshold if keep_above else end[2] <= threshold
        if start_inside:
            result.append(start)
        if start_inside != end_inside:
            fraction = (threshold - start[2]) / (end[2] - start[2])
            result.append(tuple(start[i] + fraction*(end[i] - start[i]) for i in range(3)))
    return result


def section_polygons(triangles):
    result = []
    for triangle in triangles:
        polygon = clip_at_z(list(triangle), SLICE_Z[0], True)
        if polygon:
            polygon = clip_at_z(polygon, SLICE_Z[1], False)
        if len(polygon) >= 2:
            result.append([(point[0], point[1]) for point in polygon])
    return result


def parse_landmarks():
    text = WORLD_FILE.read_text(encoding="utf-8")
    root = ET.fromstring(text)
    landmarks = {}
    for name in ("visitor_marker", "guide_marker", "staff_marker"):
        pose = root.findtext(f".//model[@name='{name}']/pose")
        values = [float(value) for value in pose.split()]
        landmarks[name] = {"x": values[0], "y": values[1], "active": True}
    match = re.search(r"<name>tiago</name>\s*<pose>([^<]+)</pose>", text)
    if not match:
        raise ValueError("Could not locate the configured TIAGo spawn")
    values = [float(value) for value in match.group(1).split()]
    landmarks["tiago_spawn"] = {"x": values[0], "y": values[1], "active": False,
                                 "note": "configured include is commented in museum.world"}
    return landmarks


def bounds_for(triangles):
    points = [point for triangle in triangles for point in triangle]
    return {axis: round(value, 4) for axis, value in (
        ("x_min", min(point[0] for point in points)),
        ("x_max", max(point[0] for point in points)),
        ("y_min", min(point[1] for point in points)),
        ("y_max", max(point[1] for point in points)),
        ("z_min", min(point[2] for point in points)),
        ("z_max", max(point[2] for point in points)),
    )}


def obstacle_mask(polygons, crop, resolution=GRID_RESOLUTION):
    width = math.ceil((crop["x_max"] - crop["x_min"]) / resolution) + 1
    height = math.ceil((crop["y_max"] - crop["y_min"]) / resolution) + 1
    image = Image.new("L", (width, height), 0)
    draw = ImageDraw.Draw(image)

    def pixel(point):
        return ((point[0] - crop["x_min"]) / resolution,
                (crop["y_max"] - point[1]) / resolution)

    for polygon in polygons:
        pixels = [pixel(point) for point in polygon]
        if len(pixels) >= 3:
            draw.polygon(pixels, fill=255)
        draw.line(pixels + [pixels[0]], fill=255, width=3)
    draw.rectangle((0, 0, width - 1, height - 1), outline=255, width=2)
    return image


def free_components(mask, crop, landmarks, minimum_area=2.0):
    width, height = mask.size
    occupied = mask.load()
    seen = bytearray(width * height)
    components = []
    for y in range(1, height - 1):
        for x in range(1, width - 1):
            key = y*width + x
            if seen[key] or occupied[x, y]:
                continue
            queue = deque([(x, y)])
            seen[key] = 1
            cells = []
            while queue:
                current_x, current_y = queue.popleft()
                cells.append((current_x, current_y))
                for next_x, next_y in ((current_x-1, current_y), (current_x+1, current_y),
                                       (current_x, current_y-1), (current_x, current_y+1)):
                    next_key = next_y*width + next_x
                    if not seen[next_key] and not occupied[next_x, next_y]:
                        seen[next_key] = 1
                        queue.append((next_x, next_y))
            area = len(cells) * GRID_RESOLUTION * GRID_RESOLUTION
            if area < minimum_area:
                continue
            xs, ys = zip(*cells)
            region_bounds = {
                "x_min": crop["x_min"] + min(xs)*GRID_RESOLUTION,
                "x_max": crop["x_min"] + max(xs)*GRID_RESOLUTION,
                "y_min": crop["y_max"] - max(ys)*GRID_RESOLUTION,
                "y_max": crop["y_max"] - min(ys)*GRID_RESOLUTION,
            }
            contained = [name for name, point in landmarks.items()
                         if region_bounds["x_min"] <= point["x"] <= region_bounds["x_max"]
                         and region_bounds["y_min"] <= point["y"] <= region_bounds["y_max"]
                         and not occupied[
                             min(width-1, max(0, round((point["x"]-crop["x_min"])/GRID_RESOLUTION))),
                             min(height-1, max(0, round((crop["y_max"]-point["y"])/GRID_RESOLUTION)))
                         ]]
            components.append({"approximate_area_m2": round(area, 1),
                               "bounds": {key: round(value, 1) for key, value in region_bounds.items()},
                               "contains_landmarks": contained})
    components.sort(key=lambda item: item["approximate_area_m2"], reverse=True)
    for index, component in enumerate(components[:8], 1):
        component["candidate_region_id"] = f"region_{index}"
    return components[:8]


def distance_to_obstacles(mask):
    width, height = mask.size
    pixels = mask.load()
    infinity = float("inf")
    distance = [0.0 if pixels[x, y] else infinity for y in range(height) for x in range(width)]
    heap = [(0.0, index) for index, value in enumerate(distance) if value == 0.0]
    heapq.heapify(heap)
    for_distance = ((-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
                    (-1, -1, math.sqrt(2)), (1, -1, math.sqrt(2)),
                    (-1, 1, math.sqrt(2)), (1, 1, math.sqrt(2)))
    while heap:
        value, index = heapq.heappop(heap)
        if value != distance[index]:
            continue
        x, y = index % width, index // width
        for dx, dy, cost in for_distance:
            nx, ny = x + dx, y + dy
            if 0 <= nx < width and 0 <= ny < height:
                neighbor = ny*width + nx
                candidate = value + cost
                if candidate < distance[neighbor]:
                    distance[neighbor] = candidate
                    heapq.heappush(heap, (candidate, neighbor))
    return distance


def widest_path_width(mask, distances, crop, start, target):
    width, height = mask.size
    def index(point):
        x = round((point[0] - crop["x_min"]) / GRID_RESOLUTION)
        y = round((crop["y_max"] - point[1]) / GRID_RESOLUTION)
        return y*width + x
    start_index, target_index = index(start), index(target)
    capacity = [-1.0] * (width*height)
    capacity[start_index] = distances[start_index]
    heap = [(-capacity[start_index], start_index)]
    pixels = mask.load()
    while heap:
        negative, current = heapq.heappop(heap)
        current_capacity = -negative
        if current == target_index:
            return round(2.0 * current_capacity * GRID_RESOLUTION, 2)
        if current_capacity != capacity[current]:
            continue
        x, y = current % width, current // width
        for nx, ny in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
            if not (0 <= nx < width and 0 <= ny < height) or pixels[nx, ny]:
                continue
            neighbor = ny*width + nx
            candidate = min(current_capacity, distances[neighbor])
            if candidate > capacity[neighbor]:
                capacity[neighbor] = candidate
                heapq.heappush(heap, (-candidate, neighbor))
    return None


def room_estimate(mask):
    # Closing openings up to roughly 1.6 m gives a deliberately coarse count
    # of architectural compartments, not semantic rooms.
    closed = mask.filter(ImageFilter.MaxFilter(17))
    dummy_landmarks = {}
    components = free_components(closed, DEMO_CROP, dummy_landmarks, minimum_area=8.0)
    count = len(components)
    if count == 0:
        return {"range": [1, 3], "method_count": 0}
    return {"range": [max(1, count - 2), count + 2], "method_count": count}


def render(polygons, bounds, landmarks, destination):
    margin_m = 2.0
    x_min, x_max = bounds["x_min"]-margin_m, bounds["x_max"]+margin_m
    y_min, y_max = bounds["y_min"]-margin_m, bounds["y_max"]+margin_m
    plot_width = 1600
    plot_height = round(plot_width * (y_max-y_min) / (x_max-x_min))
    header = 92
    image = Image.new("RGB", (plot_width, plot_height + header), "white")
    draw = ImageDraw.Draw(image)
    def pixel(point):
        return ((point[0]-x_min)/(x_max-x_min)*(plot_width-1),
                header + (y_max-point[1])/(y_max-y_min)*(plot_height-1))
    for value in range(math.ceil(x_min/5)*5, math.floor(x_max/5)*5+1, 5):
        x, _ = pixel((value, 0))
        draw.line((x, header, x, header+plot_height-1), fill="#dce3e8", width=1)
        draw.text((x+2, header+plot_height-14), str(value), fill="#65727a")
    for value in range(math.ceil(y_min/5)*5, math.floor(y_max/5)*5+1, 5):
        _, y = pixel((0, value))
        draw.line((0, y, plot_width-1, y), fill="#dce3e8", width=1)
        draw.text((2, y-12), str(value), fill="#65727a")
    for polygon in polygons:
        pixels = [pixel(point) for point in polygon]
        if len(pixels) >= 3:
            draw.polygon(pixels, fill="#4d5960")
        draw.line(pixels + [pixels[0]], fill="#263238", width=2)
    x0, y0 = pixel((0, 0))
    x_axis = pixel((5, 0)); y_axis = pixel((0, 5))
    draw.line((x0, y0, x_axis[0], x_axis[1]), fill="#c62828", width=4)
    draw.line((x0, y0, y_axis[0], y_axis[1]), fill="#2e7d32", width=4)
    draw.text((x_axis[0]+3, x_axis[1]-8), "+X", fill="#c62828")
    draw.text((y_axis[0]+3, y_axis[1]-10), "+Y north", fill="#2e7d32")
    colours = {"tiago_spawn": "#d32f2f", "visitor_marker": "#1565c0",
               "guide_marker": "#2e7d32", "staff_marker": "#6a1b9a"}
    for name, point in landmarks.items():
        x, y = pixel((point["x"], point["y"]))
        radius = 8
        draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=colours[name], outline="white", width=2)
        draw.text((x+10, y-9), name, fill=colours[name])
    crop_box = [pixel((DEMO_CROP["x_min"], DEMO_CROP["y_max"])),
                pixel((DEMO_CROP["x_max"], DEMO_CROP["y_min"]))]
    draw.rectangle((crop_box[0][0], crop_box[0][1], crop_box[1][0], crop_box[1][1]),
                   outline="#ef6c00", width=3)
    draw.text((12, 10), "Supplied museum: static collision geometry top-down audit", fill="#17252a")
    draw.text((12, 32), "World XY; obstacles intersecting z=0.15..1.20 m; 5 m grid", fill="#455a64")
    draw.text((12, 54), "Orange: recommended demo crop  |  TIAGo spawn is configured but commented out", fill="#455a64")
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, format="PNG", optimize=True)


def build_report(triangles, polygons, unit, up_axis, instance_count, landmarks):
    bounds = bounds_for(triangles)
    bounds["width_m"] = round(bounds["x_max"] - bounds["x_min"], 4)
    bounds["depth_m"] = round(bounds["y_max"] - bounds["y_min"], 4)
    bounds["height_m"] = round(bounds["z_max"] - bounds["z_min"], 4)
    mask = obstacle_mask(polygons, DEMO_CROP)
    components = free_components(mask, DEMO_CROP, landmarks)
    distances = distance_to_obstacles(mask)
    passages = []
    for name, target in (("central_to_north", (1.2, 9.0)), ("central_to_east", (35.0, 0.0))):
        width = widest_path_width(mask, distances, DEMO_CROP, (0.0, 0.0), target)
        passages.append({"route": name, "approximate_bottleneck_width_m": width,
                         "measurement": "0.10 m raster widest-path clearance diameter",
                         "caution": "static axis-independent estimate; not robot-footprint clearance"})
    estimate = room_estimate(mask)
    return {
        "schema_version": 1,
        "audit_scope": "static collision geometry only",
        "sources": {"collision_dae": str(COLLISION_DAE.relative_to(REPO_ROOT)),
                    "world": str(WORLD_FILE.relative_to(REPO_ROOT))},
        "collada_transform": {"unit_meter": unit, "up_axis": up_axis,
                              "world_mesh_pose_rpy_rad": [1.5708, 0.0, 0.0],
                              "effective_axis_mapping": {"world_x": "dae_X", "world_y": "-dae_Z", "world_z": "dae_Y"}},
        "geometry_bounds_world_m": bounds,
        "height_slice_world_m": {"z_min": SLICE_Z[0], "z_max": SLICE_Z[1]},
        "geometry_statistics": {"scene_geometry_instances": instance_count,
                                "triangles": len(triangles), "slice_polygons": len(polygons)},
        "landmarks_world_xy_m": landmarks,
        "candidate_connected_navigable_regions": components,
        "approximate_narrowest_passages": passages,
        "candidate_zones": {
            "central": {"bounds": {"x_min": -5.0, "x_max": 5.0, "y_min": -5.0, "y_max": 5.0}, "anchor": [0.0, 0.0]},
            "north": {"bounds": {"x_min": -5.0, "x_max": 5.0, "y_min": 5.0, "y_max": 20.0}, "anchor": [1.2, 9.0]},
            "east": {"bounds": {"x_min": 20.0, "x_max": 40.0, "y_min": -5.0, "y_max": 5.0}, "anchor": [35.0, 0.0]},
        },
        "recommended_demo_crop_world_m": DEMO_CROP,
        "physically_distinct_room_or_gallery_estimate": {
            "cautious_range": estimate["range"],
            "coarse_compartment_count_in_crop": estimate["method_count"],
            "basis": "free-space components after closing openings by about 1.6 m in the bounded crop",
            "not_semantic_labels": True,
        },
        "ambiguities": [
            "Open doorways connect architectural compartments, so connected free space is not a room count.",
            "The 2D slice cannot distinguish intentional doorways from mesh gaps or classify gallery purpose.",
            "Thin surfaces are rasterised with a conservative 0.3 m line width for connectivity analysis.",
            "The room estimate covers the recommended crop, not the full 122 m-wide visual complex.",
            "TIAGo is configured at the reported spawn, but its include is commented out in the packaged world.",
        ],
    }, bounds


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    started = time.perf_counter()
    triangles, unit, up_axis, instance_count = load_world_geometry()
    polygons = section_polygons(triangles)
    landmarks = parse_landmarks()
    report, bounds = build_report(triangles, polygons, unit, up_axis, instance_count, landmarks)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    render(polygons, bounds, landmarks, args.output_dir / "topdown.png")
    runtime = time.perf_counter() - started
    report["script_runtime_seconds"] = round(runtime, 3)
    (args.output_dir / "layout_report.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(f"Exported {args.output_dir / 'topdown.png'}")
    print(f"Exported {args.output_dir / 'layout_report.json'}")
    print(f"Runtime: {runtime:.3f} seconds")


if __name__ == "__main__":
    main()
