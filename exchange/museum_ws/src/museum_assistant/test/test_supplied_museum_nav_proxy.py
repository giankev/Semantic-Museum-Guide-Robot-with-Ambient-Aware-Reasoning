import hashlib
import importlib.util
import json
import math
from pathlib import Path
import subprocess
import sys
import unittest
import xml.etree.ElementTree as ET


REPO_ROOT = Path(__file__).resolve().parents[5]
PACKAGE = REPO_ROOT / "exchange/museum_ws/src/museum_assistant"
WORLD = PACKAGE / "worlds/supplied_museum/museum_nav.world"
SCRIPT = REPO_ROOT / "scripts/generate_map_from_sdf_boxes.py"
MAP_DIR = PACKAGE / "maps"
AUDIT_DIR = REPO_ROOT / ".museum_layout_audit"
PREFIXES = ("nav_boundary_", "nav_wall_", "nav_obstacle_")


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_map_from_sdf_boxes", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def artifact_hashes():
    paths = (
        MAP_DIR / "supplied_museum_nav.pgm",
        MAP_DIR / "supplied_museum_nav.yaml",
        AUDIT_DIR / "nav_proxy_overlay.png",
        AUDIT_DIR / "nav_proxy_report.json",
        AUDIT_DIR / "multi_room_demo_overlay.png",
        AUDIT_DIR / "multi_room_demo_report.json",
    )
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in paths}


class SuppliedMuseumNavProxyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        command = [sys.executable, str(SCRIPT)]
        subprocess.run(command, cwd=REPO_ROOT, check=True, capture_output=True, text=True, timeout=30)
        first = artifact_hashes()
        subprocess.run(command, cwd=REPO_ROOT, check=True, capture_output=True, text=True, timeout=30)
        cls.deterministic = first == artifact_hashes()
        cls.root = ET.parse(WORLD).getroot()
        cls.generator = load_generator()
        cls.boxes = cls.generator.load_boxes()
        cls.report = json.loads((AUDIT_DIR / "multi_room_demo_report.json").read_text(encoding="utf-8"))
        cls.pgm = (MAP_DIR / "supplied_museum_nav.pgm").read_bytes()
        cls.pgm_body = cls.pgm.split(b"255\n", 1)[1]
        cls.width = cls.report["occupancy_map"]["width_cells"]
        cls.height = cls.report["occupancy_map"]["height_cells"]

    def map_value(self, x, y):
        column, row = self.generator.world_to_cell(x, y, self.width, self.height)
        return self.pgm_body[row * self.width + column]

    def test_world_parses_and_original_mesh_is_visual_only(self):
        self.assertEqual(self.root.tag, "sdf")
        visual_meshes = [
            element.text
            for element in self.root.findall(".//visual/geometry/mesh/uri")
        ]
        self.assertEqual(visual_meshes[0], "model.dae")
        self.assertEqual(
            visual_meshes[1:],
            ["humans/person_standing/meshes/standing.dae"] * 3,
        )
        self.assertEqual(self.root.findall(".//collision/geometry/mesh/uri"), [])

    def test_navigation_boxes_are_finite_positive_axis_aligned_boxes(self):
        for box in self.boxes:
            self.assertTrue(all(math.isfinite(box[key]) for key in ("x", "y", "z", "size_x", "size_y", "size_z")))
            self.assertTrue(all(box[key] > 0 for key in ("size_x", "size_y", "size_z")))
        for model in self.root.findall(".//model"):
            if model.attrib.get("name", "").startswith(PREFIXES):
                for element in (model, *model.findall("link"), *model.findall("link/collision")):
                    self.assertEqual(self.generator.pose_values(element)[3:], [0.0, 0.0, 0.0])

    def test_proxy_box_count_is_bounded_and_southern_geometry_exists(self):
        self.assertEqual(len(self.boxes), 23)
        self.assertEqual(self.report["number_of_navigation_boxes"], 23)
        self.assertLessEqual(len(self.boxes), 40)
        south = [box for box in self.boxes if box["name"].startswith(("nav_wall_south_", "nav_obstacle_south_"))]
        self.assertEqual(len(south), 10)

    def test_original_inner_panels_are_laser_visible_proxy_boxes(self):
        boxes = {box["name"]: box for box in self.boxes}
        expected = {
            "nav_obstacle_south_west_inner_panel": -2.5115,
            "nav_obstacle_south_east_inner_panel": 2.5115,
        }
        for name, center_x in expected.items():
            box = boxes[name]
            self.assertEqual(box["x"], center_x)
            self.assertEqual(box["y"], -18.8)
            self.assertEqual(box["size_x"], 2.523)
            self.assertEqual(box["size_y"], 1.0)

    def test_existing_three_grounded_landmarks_are_preserved(self):
        landmarks = [box for box in self.boxes if box["name"].startswith("nav_obstacle_landmark_")]
        self.assertEqual(len(landmarks), 3)
        for box in landmarks:
            self.assertLessEqual(box["z"] - box["size_z"] / 2, 0.15)
            self.assertGreaterEqual(box["z"] + box["size_z"] / 2, 1.20)

    def test_original_west_central_panels_are_laser_visible_proxy_boxes(self):
        boxes = {box["name"]: box for box in self.boxes}
        expected = {
            "nav_obstacle_central_west_north_panel": 3.475,
            "nav_obstacle_central_west_south_panel": -2.525,
        }
        for name, center_y in expected.items():
            box = boxes[name]
            self.assertEqual(box["x"], -7.225)
            self.assertEqual(box["y"], center_y)
            self.assertEqual(box["size_x"], 1.15)
            self.assertEqual(box["size_y"], 3.15)
            self.assertEqual(self.map_value(box["x"], box["y"]), 0)

    def test_crop_boundaries_match_compact_region(self):
        boxes = {box["name"]: box for box in self.boxes}
        self.assertEqual(boxes["nav_boundary_west"]["x"], -17.5)
        self.assertEqual(boxes["nav_boundary_east"]["x"], 22.2)
        self.assertEqual(boxes["nav_boundary_south"]["y"], -24.5)
        self.assertEqual(boxes["nav_boundary_north"]["y"], 22.0)

    def test_pgm_yaml_and_trinary_values_agree(self):
        yaml_text = (MAP_DIR / "supplied_museum_nav.yaml").read_text(encoding="utf-8")
        self.assertIn("origin: [-17.5, -24.5, 0.0]", yaml_text)
        self.assertIn(b"794 930\n255\n", self.pgm[:100])
        self.assertEqual(set(self.pgm_body), {0, 205, 254})

    def test_candidates_are_free_and_clear(self):
        for candidate in self.report["candidate_poses"].values():
            self.assertTrue(candidate["free"])
            self.assertGreaterEqual(candidate["clearance_m"], 0.75)

    def test_markers_and_candidates_do_not_intersect_boxes(self):
        points = [*self.report["marker_positions"].values(), *self.report["candidate_poses"].values()]
        for point in points:
            for box in self.boxes:
                dx = max(abs(point["x"] - box["x"]) - box["size_x"] / 2, 0.0)
                dy = max(abs(point["y"] - box["y"]) - box["size_y"] / 2, 0.0)
                self.assertGreaterEqual(math.hypot(dx, dy), 0.18)

    def test_staff_marker_is_relocated_inside_compact_crop(self):
        self.assertEqual(self.report["marker_positions"]["staff_marker"], {"x": 3.5, "y": 4.0})
        self.assertEqual(self.report["marker_relocation"]["staff_marker"]["public_adapter_id"], "staff_1")

    def test_unknown_is_not_free(self):
        self.assertEqual(self.map_value(18.0, -14.0), 205)
        self.assertNotEqual(self.map_value(18.0, -14.0), 254)

    def test_occupied_geometry_overrides_free_rasterization(self):
        self.assertEqual(self.report["occupancy_map"]["occupied_value"], 0)
        self.assertEqual(self.map_value(-17.5, -20.0), 0)

    def test_repeated_generation_is_deterministic(self):
        self.assertTrue(self.deterministic)


if __name__ == "__main__":
    unittest.main()
