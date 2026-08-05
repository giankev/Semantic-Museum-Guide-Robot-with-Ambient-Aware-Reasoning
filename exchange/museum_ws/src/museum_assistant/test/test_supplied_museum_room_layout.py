import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys

import yaml


REPO_ROOT = Path(__file__).resolve().parents[5]
PACKAGE = REPO_ROOT / "exchange/museum_ws/src/museum_assistant"
LAYOUT_PATH = PACKAGE / "config/supplied_museum_room_layout.yaml"
OVERRIDE_PATH = PACKAGE / "config/nav2_ground_truth_odom_override.yaml"
NAV2_PATH = PACKAGE / "config/nav2_museum.yaml"
SCRIPT = REPO_ROOT / "scripts/generate_map_from_sdf_boxes.py"
REPORT_PATH = REPO_ROOT / ".museum_layout_audit/multi_room_demo_report.json"


def load_generator():
    spec = importlib.util.spec_from_file_location("compact_proxy_generator", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


subprocess.run([sys.executable, str(SCRIPT)], cwd=REPO_ROOT, check=True,
               capture_output=True, text=True, timeout=30)
LAYOUT = yaml.safe_load(LAYOUT_PATH.read_text(encoding="utf-8"))
REPORT = json.loads(REPORT_PATH.read_text(encoding="utf-8"))
GENERATOR = load_generator()
WIDTH = REPORT["occupancy_map"]["width_cells"]
HEIGHT = REPORT["occupancy_map"]["height_cells"]
PGM = (PACKAGE / "maps/supplied_museum_nav.pgm").read_bytes().split(b"255\n", 1)[1]


def map_value(x, y):
    column, row = GENERATOR.world_to_cell(x, y, WIDTH, HEIGHT)
    return PGM[row * WIDTH + column]


def in_bounds(point, bounds):
    return (bounds["x_min"] <= point["x"] <= bounds["x_max"] and
            bounds["y_min"] <= point["y"] <= bounds["y_max"])


def test_crop_includes_all_three_demo_galleries():
    crop = LAYOUT["crop"]
    for name in ("north_gallery", "south_west_gallery", "south_east_gallery"):
        for region in LAYOUT["physical_areas"][name]["validated_free_regions"]:
            bounds = region["bounds"]
            assert crop["x_min"] <= bounds["x_min"] < bounds["x_max"] <= crop["x_max"]
            assert crop["y_min"] <= bounds["y_min"] < bounds["y_max"] <= crop["y_max"]


def test_exactly_four_demo_gallery_candidates_exist():
    assert REPORT["demo_gallery_candidates"] == [
        "candidate_central_gallery", "candidate_north",
        "candidate_south_west", "candidate_south_east"
    ]


def test_candidate_north_is_unchanged():
    north = LAYOUT["candidate_poses"]["candidate_north"]
    assert (north["x"], north["y"], north["yaw"]) == (0.0, 16.0, 1.5708)


def test_southern_candidates_are_in_distinct_gallery_regions():
    for candidate_name, area_name in (("candidate_south_west", "south_west_gallery"),
                                      ("candidate_south_east", "south_east_gallery")):
        point = LAYOUT["candidate_poses"][candidate_name]
        regions = LAYOUT["physical_areas"][area_name]["validated_free_regions"]
        assert any(in_bounds(point, region["bounds"]) for region in regions)
    assert LAYOUT["candidate_poses"]["candidate_south_west"]["area"] != LAYOUT["candidate_poses"]["candidate_south_east"]["area"]


def test_every_demo_candidate_is_free():
    for name in REPORT["demo_gallery_candidates"]:
        point = REPORT["candidate_poses"][name]
        assert point["free"] and map_value(point["x"], point["y"]) == 254


def test_every_demo_candidate_has_required_clearance():
    assert all(REPORT["candidate_poses"][name]["clearance_m"] >= 0.75
               for name in REPORT["demo_gallery_candidates"])


def test_candidates_are_not_in_door_regions():
    for point in LAYOUT["candidate_poses"].values():
        assert not any(in_bounds(point, door["map_free_region"])
                       for door in LAYOUT["doors"].values())


def test_southern_candidates_are_outside_central_corridor():
    central = LAYOUT["physical_areas"]["central_area"]["validated_free_regions"]
    for name in ("candidate_south_west", "candidate_south_east"):
        assert not any(in_bounds(LAYOUT["candidate_poses"][name], region["bounds"])
                       for region in central)


def test_topology_references_only_existing_areas_and_doors():
    areas, doors = set(LAYOUT["physical_areas"]), set(LAYOUT["doors"])
    for edge in LAYOUT["topology"]:
        assert edge["from"] in areas and edge["connected_to"] in areas
        assert edge["door"] in doors


def test_every_southern_gallery_is_connected_to_central_area():
    edges = {(edge["from"], edge["connected_to"]) for edge in LAYOUT["topology"]}
    assert ("central_area", "south_west_gallery") in edges
    assert ("central_area", "south_east_gallery") in edges


def test_every_accepted_door_has_required_usable_width():
    for door in REPORT["doors"].values():
        assert door["occupied_map_width"] <= door["raw_geometric_width"]
        assert door["usable_width"] >= 1.5


def test_unknown_cells_exist_and_are_not_free():
    counts = REPORT["occupancy_map"]["cell_counts"]
    assert counts["unknown"] > 0
    assert LAYOUT["map"]["unknown_value"] != LAYOUT["map"]["free_value"]
    assert yaml.safe_load(NAV2_PATH.read_text(encoding="utf-8"))["planner_server"]["ros__parameters"]["GridBased"]["allow_unknown"] is False


def test_validated_room_regions_contain_no_occupied_cells():
    for area in LAYOUT["physical_areas"].values():
        for region in area["validated_free_regions"]:
            bounds = region["bounds"]
            x = bounds["x_min"] + 0.025
            while x < bounds["x_max"]:
                y = bounds["y_min"] + 0.025
                while y < bounds["y_max"]:
                    assert map_value(x, y) != 0
                    y += 0.05
                x += 0.05


def test_occupied_geometry_overrides_free_space_rasterization():
    boxes = GENERATOR.load_boxes()
    synthetic = {"name": "nav_obstacle_test", "x": 0.0, "y": 0.0, "z": 1.0,
                 "size_x": 0.2, "size_y": 0.2, "size_z": 2.0}
    width, height, cells = GENERATOR.rasterize(boxes + [synthetic])
    assert GENERATOR.map_value(0.0, 0.0, width, height, cells) == 0


def test_map_generation_is_deterministic():
    first = (PACKAGE / "maps/supplied_museum_nav.pgm").read_bytes()
    subprocess.run([sys.executable, str(SCRIPT)], cwd=REPO_ROOT, check=True,
                   capture_output=True, text=True, timeout=30)
    assert first == (PACKAGE / "maps/supplied_museum_nav.pgm").read_bytes()


def test_map_dimensions_and_origin_match_crop():
    occupancy = REPORT["occupancy_map"]
    assert (occupancy["width_cells"], occupancy["height_cells"]) == (794, 930)
    assert occupancy["origin"] == [-17.5, -24.5, 0.0]


def test_no_duplicate_east_candidate_exists():
    assert "candidate_east" not in LAYOUT["candidate_poses"]
    assert LAYOUT["experimental_east_area"]["demo"] is False
    assert LAYOUT["experimental_east_area"]["validated_navigation"] is False


def test_no_marker_intersects_a_wall_or_candidate():
    markers = REPORT["marker_positions"]
    boxes = REPORT["navigation_boxes"]
    for marker in markers.values():
        for box in boxes:
            dx = max(abs(marker["x"] - box["x"]) - box["size_x"] / 2, 0.0)
            dy = max(abs(marker["y"] - box["y"]) - box["size_y"] / 2, 0.0)
            assert math.hypot(dx, dy) >= 0.18
        for candidate in REPORT["candidate_poses"].values():
            assert math.hypot(marker["x"] - candidate["x"], marker["y"] - candidate["y"]) >= 0.46


def test_total_proxy_box_count_is_bounded():
    assert REPORT["number_of_navigation_boxes"] == 19
    assert REPORT["number_of_navigation_boxes"] <= REPORT["navigation_box_limit"] == 40


def test_all_required_nav2_odometry_consumers_are_resolved():
    override = yaml.safe_load(OVERRIDE_PATH.read_text(encoding="utf-8"))
    expected = {"controller_server", "bt_navigator", "velocity_smoother"}
    assert set(override) == expected
    assert all(override[node]["ros__parameters"]["odom_topic"] == "/museum/ground_truth_odom"
               for node in expected)
    assert set(REPORT["nav2_odometry_topic_audit"]["explicit_consumers"]) == expected
