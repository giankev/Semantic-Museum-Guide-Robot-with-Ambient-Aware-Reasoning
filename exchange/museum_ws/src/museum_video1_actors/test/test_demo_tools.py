"""Run with Python unittest; no ROS mocks or robotics installation required."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

PACKAGE = Path(__file__).resolve().parents[1]
REPO = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(PACKAGE/'scripts'))
sys.path.insert(0, str(REPO/'scripts'))
from demo_math import alignment, rotate, speed_stats, transform
from prepare_video1_animated_world import prepare


class DemoTests(unittest.TestCase):
    def test_alignment_with_nonzero_spawn_and_rotation(self):
        raw = (5.0, -3.0, 1.2)
        odom = (1.0, 2.0, -0.4)
        a = alignment(raw, odom)
        x, y = transform(*raw[:2], a)
        self.assertAlmostEqual(x, odom[0]); self.assertAlmostEqual(y, odom[1])
        dx, dy = rotate(0.0, 0.3, a[2])
        px, py = transform(raw[0], raw[1]+0.3, a)
        self.assertAlmostEqual(px-x, dx); self.assertAlmostEqual(py-y, dy)
        self.assertAlmostEqual(math.hypot(dx, dy), 0.3)

    def test_statistics_preserve_zeros_spikes_and_duplicate_stamps(self):
        s = speed_stats([(0, 0, 0), (0.05, 0.2, 0), (0.05, 2.0, 0)])
        self.assertEqual(s['zero_samples'], 1)
        self.assertEqual(s['over_1mps_samples'], 1)
        self.assertEqual(s['nonpositive_stamp_intervals'], 1)
        self.assertAlmostEqual(s['above_0_10_percent'], 200/3)

    def test_speed_statistics_on_regular_stream(self):
        s = speed_stats([(i/20, 0.2, 0.0) for i in range(201)])
        self.assertAlmostEqual(s['sim_hz'], 20)
        self.assertAlmostEqual(s['mean_mps'], 0.2)
        self.assertEqual(s['above_0_10_percent'], 100)
        self.assertEqual(s['max_acceleration_mps2'], 0)

    def test_nonfinite_statistics_are_not_a_pass(self):
        self.assertTrue(speed_stats([(0, float('nan'), 0)])['invalid'])

    def test_disposable_world_preserves_static_collision_geometry(self):
        source = REPO/'exchange/museum_ws/src/museum_assistant/worlds/supplied_museum/museum_nav.world'
        before = source.read_bytes()
        original = ET.fromstring(before).find('world')
        config = json.loads((PACKAGE/'config/one_actor.json').read_text())
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)/'baseline.world'
            manifest = prepare(source, target, 'baseline', config)
            generated = ET.parse(target).getroot().find('world')
            names = {m.get('name') for m in generated.findall('model')}
            self.assertFalse(names & {'visitor_marker', 'guide_marker', 'staff_marker'})
            for m in original.findall('model'):
                if m.get('name').startswith('nav_') or m.get('name') == 'floor':
                    match = generated.find(f"model[@name='{m.get('name')}']")
                    self.assertEqual(ET.tostring(m), ET.tostring(match))
            self.assertEqual(ET.tostring(original.find('plugin')), ET.tostring(generated.find('plugin')))
            self.assertEqual(manifest['actor_count'], 0)
            self.assertEqual(source.read_bytes(), before)
            self.assertEqual(manifest['source_world_sha256'], hashlib.sha256(before).hexdigest())

    def test_source_world_cannot_be_overwritten(self):
        with self.assertRaises(ValueError):
            prepare('/tmp/source.world', '/tmp/source.world', 'baseline', {})

    def test_candidate_lane_clears_all_proxy_walls(self):
        c = json.loads((PACKAGE/'config/one_actor.json').read_text())
        world = ET.parse(REPO/'exchange/museum_ws/src/museum_assistant/worlds/supplied_museum/museum_nav.world').getroot()
        boxes = []
        for model in world.findall('./world/model'):
            if model.get('name').startswith('nav_'):
                x, y, *_ = map(float, model.find('pose').text.split())
                sx, sy, _ = map(float, model.find('./link/collision/geometry/box/size').text.split())
                boxes.append((x, y, sx/2, sy/2, model.get('name')))
        for i in range(1000):
            a=2*math.pi*i/1000
            x, y = c['cx']+c['rx']*math.cos(a), c['cy']+c['ry']*math.sin(a)
            for bx, by, hx, hy, name in boxes:
                distance=math.hypot(max(0, abs(x-bx)-hx), max(0, abs(y-by)-hy))
                self.assertGreater(distance, 0.35, name)

    def test_only_one_navigation_send_and_no_robot_teleport(self):
        import ast
        tree = ast.parse((PACKAGE/'scripts/record_demo.py').read_text())
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)
                 and isinstance(n.func, ast.Attribute) and n.func.attr == 'send_goal_async']
        self.assertEqual(len(calls), 1)
        self.assertNotIn('SetEntityState', (PACKAGE/'scripts/record_demo.py').read_text())


if __name__ == '__main__':
    unittest.main()
