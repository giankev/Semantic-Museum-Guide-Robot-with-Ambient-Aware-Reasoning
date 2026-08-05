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
WORLD = REPO_ROOT / "exchange/museum_ws/src/museum_assistant/worlds/supplied_museum/museum_nav.world"
SCRIPT = REPO_ROOT / "scripts/generate_map_from_sdf_boxes.py"
MAP_DIR = REPO_ROOT / "exchange/museum_ws/src/museum_assistant/maps"
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
        cls.report = json.loads((AUDIT_DIR / "nav_proxy_report.json").read_text(encoding="utf-8"))
        cls.pgm = (MAP_DIR / "supplied_museum_nav.pgm").read_bytes()

    def test_world_parses_as_xml(self):
        self.assertEqual(self.root.tag, "sdf")

    def test_original_mesh_is_visual_only(self):
        visual_uris = [element.text for element in self.root.findall(".//visual/geometry/mesh/uri")]
        collision_uris = [element.text for element in self.root.findall(".//collision/geometry/mesh/uri")]
        self.assertEqual(visual_uris, ["model.dae"])
        self.assertEqual(collision_uris, [])

    def test_navigation_boxes_have_finite_dimensions_and_poses(self):
        for box in self.boxes:
            self.assertTrue(all(math.isfinite(box[key]) for key in ("x", "y", "z", "size_x", "size_y", "size_z")))

    def test_navigation_boxes_are_axis_aligned(self):
        for model in self.root.findall(".//model"):
            if model.attrib.get("name", "").startswith(PREFIXES):
                for element in (model, *model.findall("link"), *model.findall("link/collision")):
                    self.assertEqual(self.generator.pose_values(element)[3:], [0.0, 0.0, 0.0])

    def test_navigation_box_dimensions_are_positive(self):
        for box in self.boxes:
            self.assertGreater(box["size_x"], 0)
            self.assertGreater(box["size_y"], 0)
            self.assertGreater(box["size_z"], 0)

    def test_navigation_box_count_is_bounded(self):
        self.assertLessEqual(len(self.boxes), 35)

    def test_crop_boundaries_are_closed(self):
        boxes = {box["name"]: box for box in self.boxes}
        self.assertEqual(boxes["nav_boundary_west"]["x"], -8.0)
        self.assertEqual(boxes["nav_boundary_east"]["x"], 42.0)
        self.assertEqual(boxes["nav_boundary_south"]["y"], -8.0)
        self.assertEqual(boxes["nav_boundary_north"]["y"], 22.0)
        self.assertGreaterEqual(boxes["nav_boundary_west"]["size_y"], 30.0)
        self.assertGreaterEqual(boxes["nav_boundary_south"]["size_x"], 50.0)

    def test_markers_do_not_intersect_navigation_boxes(self):
        for marker in self.report["marker_positions"].values():
            for box in self.boxes:
                dx = max(abs(marker["x"]-box["x"])-box["size_x"]/2, 0.0)
                dy = max(abs(marker["y"]-box["y"])-box["size_y"]/2, 0.0)
                self.assertGreaterEqual(math.hypot(dx, dy), 0.18)

    def test_pgm_and_yaml_exist_and_agree(self):
        yaml_text = (MAP_DIR / "supplied_museum_nav.yaml").read_text(encoding="utf-8")
        self.assertIn("image: supplied_museum_nav.pgm", yaml_text)
        self.assertTrue(self.pgm.startswith(b"P5\n"))
        self.assertIn(b"1000 600\n255\n", self.pgm[:100])

    def test_resolution_is_five_centimetres(self):
        self.assertEqual(self.report["occupancy_map"]["resolution_m_per_cell"], 0.05)

    def test_map_origin_matches_crop(self):
        self.assertEqual(self.report["occupancy_map"]["origin"], [-8.0, -8.0, 0.0])

    def test_repeated_generation_is_deterministic(self):
        self.assertTrue(self.deterministic)

    def test_candidates_are_free(self):
        self.assertTrue(all(candidate["free"] for candidate in self.report["candidate_poses"].values()))

    def test_candidates_have_required_clearance(self):
        for candidate in self.report["candidate_poses"].values():
            self.assertGreaterEqual(candidate["clearance_m"], 0.75)

    def test_candidates_do_not_overlap_markers(self):
        for candidate in self.report["candidate_poses"].values():
            for marker in self.report["marker_positions"].values():
                self.assertGreaterEqual(
                    math.hypot(candidate["x"]-marker["x"], candidate["y"]-marker["y"]),
                    0.46,
                )

    def test_pgm_rows_follow_ros_world_y_orientation(self):
        body = self.pgm.split(b"255\n", 1)[1]
        width, height = 1000, 600
        def value_at(x, y):
            column = math.floor((x + 8.0) / 0.05)
            row = height - 1 - math.floor((y + 8.0) / 0.05)
            return body[row*width + column]
        self.assertEqual(value_at(7.0, 2.0), 0)
        self.assertEqual(value_at(7.0, -2.0), 254)

    def test_central_to_north_opening_is_wide_enough(self):
        self.assertGreaterEqual(self.report["openings"]["central_to_north"]["width_m"], 1.5)

    def test_central_to_east_opening_is_wide_enough(self):
        self.assertGreaterEqual(self.report["openings"]["central_to_east"]["width_m"], 1.5)


if __name__ == "__main__":
    unittest.main()
