import importlib.util
import math
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[5]
PACKAGE = REPO_ROOT / "exchange/museum_ws/src/museum_assistant"
ROUTES_PATH = PACKAGE / "config/supplied_museum_routes.yaml"
LAYOUT_PATH = PACKAGE / "config/supplied_museum_room_layout.yaml"
SCRIPT = REPO_ROOT / "scripts/generate_map_from_sdf_boxes.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("route_map_generator", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


ROUTES = yaml.safe_load(ROUTES_PATH.read_text(encoding="utf-8"))
LAYOUT = yaml.safe_load(LAYOUT_PATH.read_text(encoding="utf-8"))
GENERATOR = load_generator()
WIDTH, HEIGHT, CELLS = GENERATOR.rasterize(GENERATOR.load_boxes())
FREE = LAYOUT["map"]["free_value"]
START = LAYOUT["candidate_poses"]["candidate_start"]


def pose(name):
    return ROUTES["route_nodes"].get(name, ROUTES["candidate_poses"].get(name))


def samples_between(first, second, spacing=0.025):
    distance = math.hypot(second["x"] - first["x"], second["y"] - first["y"])
    count = max(1, math.ceil(distance / spacing))
    for index in range(count + 1):
        ratio = index / count
        yield (first["x"] + ratio * (second["x"] - first["x"]),
               first["y"] + ratio * (second["y"] - first["y"]))


def test_required_route_nodes_and_routes_exist():
    assert set(ROUTES["route_nodes"]) == {
        "south_entry", "south_junction", "south_inner_gap",
        "south_west_door_approach", "south_east_door_approach",
    }
    assert set(ROUTES["routes"]) == {
        "north_gallery", "south_west_gallery", "south_east_gallery",
    }
    assert ROUTES["routes"]["north_gallery"] == ["candidate_north"]


def test_every_route_node_is_known_free_with_required_clearance():
    doors = LAYOUT["doors"].values()
    for node in ROUTES["route_nodes"].values():
        assert GENERATOR.map_value(node["x"], node["y"], WIDTH, HEIGHT, CELLS) == FREE
        measured = GENERATOR.clearance_from_map(node, WIDTH, HEIGHT, CELLS)
        assert measured >= 0.75
        assert node["clearance_m"] == measured
        assert not any(
            door["map_free_region"]["x_min"] <= node["x"] <= door["map_free_region"]["x_max"]
            and door["map_free_region"]["y_min"] <= node["y"] <= door["map_free_region"]["y_max"]
            for door in doors
        )


def test_route_nodes_do_not_intersect_proxy_boxes_or_markers():
    boxes = GENERATOR.load_boxes()
    markers = GENERATOR.marker_positions()
    for node in ROUTES["route_nodes"].values():
        assert all(not (
            abs(node["x"] - box["x"]) <= box["size_x"] / 2
            and abs(node["y"] - box["y"]) <= box["size_y"] / 2
        ) for box in boxes)
        assert all(math.hypot(node["x"] - marker["x"], node["y"] - marker["y"]) > 0.46
                   for marker in markers.values())


def test_every_route_segment_stays_in_known_free_cells():
    for names in ROUTES["routes"].values():
        points = [START] + [pose(name) for name in names]
        for first, second in zip(points, points[1:]):
            for x, y in samples_between(first, second):
                assert GENERATOR.map_value(x, y, WIDTH, HEIGHT, CELLS) == FREE


def test_southern_routes_share_then_branch_in_physical_order():
    west = ROUTES["routes"]["south_west_gallery"]
    east = ROUTES["routes"]["south_east_gallery"]
    assert west[:3] == east[:3] == [
        "south_entry", "south_junction", "south_inner_gap"
    ]
    assert west[3:] != east[3:]
    entry, junction = pose("south_entry"), pose("south_junction")
    inner_gap = pose("south_inner_gap")
    west_approach = pose("south_west_door_approach")
    east_approach = pose("south_east_door_approach")
    assert (
        START["y"] > entry["y"] > junction["y"]
        > inner_gap["y"] > west_approach["y"]
    )
    assert west_approach["y"] == east_approach["y"]
    assert west_approach["x"] < junction["x"] < east_approach["x"]


def test_no_route_has_duplicate_or_zero_length_consecutive_waypoints():
    for names in ROUTES["routes"].values():
        assert len(names) == len(set(names))
        points = [START] + [pose(name) for name in names]
        assert all(math.hypot(second["x"] - first["x"], second["y"] - first["y"]) > 0.0
                   for first, second in zip(points, points[1:]))


def test_route_yaws_follow_the_centerline_and_door_segments():
    expected = {
        "south_entry": -1.5708,
        "south_junction": -1.5708,
        "south_inner_gap": -1.5708,
        "south_west_door_approach": -3.1016,
        "south_east_door_approach": -0.0400,
    }
    assert {name: node["yaw"] for name, node in ROUTES["route_nodes"].items()} == expected


def test_final_southern_poses_are_exact_and_match_the_layout():
    expected = {
        "candidate_south_west": (-10.0, -21.5, 1.5708),
        "candidate_south_east": (10.0, -21.5, 1.5708),
    }
    for name, values in expected.items():
        route_pose = ROUTES["candidate_poses"][name]
        layout_pose = LAYOUT["candidate_poses"][name]
        assert (route_pose["x"], route_pose["y"], route_pose["yaw"]) == values
        assert (layout_pose["x"], layout_pose["y"], layout_pose["yaw"]) == values
