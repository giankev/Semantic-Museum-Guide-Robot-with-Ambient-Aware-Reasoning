"""Real Humble audit regression checks, including invalid optional evidence."""
import importlib.util
import math
from pathlib import Path
import subprocess
import sys
import unittest

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE / 'scripts'))
from nav_msgs.msg import OccupancyGrid
from runtime_audit import cell_at


class RuntimeAuditTests(unittest.TestCase):
    def test_costmap_origin_rotation_and_upper_boundary(self):
        grid = OccupancyGrid()
        grid.info.resolution = 1.0
        grid.info.width, grid.info.height = 2, 1
        grid.info.origin.position.x = 10.0
        grid.info.origin.orientation.z = math.sin(math.pi / 4)
        grid.info.origin.orientation.w = math.cos(math.pi / 4)
        grid.data = [0, 100]
        self.assertEqual(cell_at(grid, 9.5, 0.5), 0)
        self.assertEqual(cell_at(grid, 9.5, 1.5), 100)
        self.assertIsNone(cell_at(grid, 9.5, 2.1))

    def test_controller_gate_distinguishes_active_and_inactive_with_humble_colors(self):
        path = PACKAGE.parent / 'museum_assistant/launch/tiago_supplied_museum_ground_truth_odom.launch.py'
        spec = importlib.util.spec_from_file_location('odom_launch', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        command = module._controller_reloader_command()
        pipeline = command.split('ros2 control list_controllers 2>/dev/null | ')[1].split(' && ready=true')[0]
        for state in ('active', 'inactive', 'unconfigured'):
            for color in ('', '\x1b[92m'):
                line = f'{color}mobile_base_controller \x1b[0m diff_drive_controller/DiffDriveController {color}{state}\x1b[0m\n'
                result = subprocess.run(['bash', '-c', pipeline], input=line, text=True)
                self.assertEqual(result.returncode == 0, state == 'active', repr(line))


if __name__ == '__main__':
    unittest.main()
