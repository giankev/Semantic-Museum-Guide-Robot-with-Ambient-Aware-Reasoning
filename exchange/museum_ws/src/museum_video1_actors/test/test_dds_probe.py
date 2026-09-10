"""Exercise actual separate-process DDS admission, without Gazebo or robot actions."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, QoSProfile
from controller_manager_msgs.srv import ListControllers
from nav_msgs.msg import OccupancyGrid
from rosgraph_msgs.msg import Clock
from social_nav_msgs.msg import Pedestrian, Pedestrians

PROBE = Path(__file__).resolve().parents[1]/'scripts/probe_dds.py'


class ProbeTests(unittest.TestCase):
    def test_new_process_receives_topics_and_service_while_parent_is_alive(self):
        rclpy.init(args=[])
        node = Node('test_dds_stack_fixture')
        clock_pub = node.create_publisher(Clock, '/clock', 10)
        map_pub = node.create_publisher(OccupancyGrid, '/map',
                                       QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        people_pub = node.create_publisher(Pedestrians, '/people', 10)
        node.create_service(ListControllers, '/controller_manager/list_controllers', lambda _, response: response)
        grid = OccupancyGrid()
        grid.info.width = grid.info.height = 1
        grid.info.resolution = 1.0
        grid.data = [0]
        map_pub.publish(grid)  # only once: late subscriber must receive latched map
        people = Pedestrians()
        person = Pedestrian()
        person.identifier = 'walker_1'
        people.pedestrians = [person]
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'probe.json'
            child = subprocess.Popen([sys.executable, str(PROBE), '--output', str(output), '--timeout', '10'],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            try:
                tick = 1
                deadline = time.monotonic()+15
                while child.poll() is None and time.monotonic() < deadline:
                    message = Clock()
                    message.clock.sec = tick
                    tick += 1
                    clock_pub.publish(message)
                    people_pub.publish(people)
                    rclpy.spin_once(node, timeout_sec=0.05)
                stdout, stderr = child.communicate(timeout=2)
                self.assertEqual(child.returncode, 0, stdout+stderr)
                result = json.loads(output.read_text())
                self.assertNotEqual(result['pid'], os.getpid())
                self.assertEqual(result['status'], 'PASS')
                self.assertTrue(result['participant_created'])
                self.assertTrue(result['controller_manager_responded'])
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait()
                node.destroy_node()
                rclpy.shutdown()

    def test_exhausted_unicast_ports_fail_new_participant_creation(self):
        # Test-only ceiling of zero makes exhaustion deterministic with two UDP
        # sockets. The launcher never installs this XML or raises any ceiling.
        domain = 181
        config = ('<CycloneDDS><Domain><General><AllowMulticast>false</AllowMulticast></General>'
                  '<Discovery><ParticipantIndex>auto</ParticipantIndex>'
                  '<MaxAutoParticipantIndex>0</MaxAutoParticipantIndex></Discovery></Domain></CycloneDDS>')
        sockets = []
        try:
            for offset in (10, 11):
                sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
                sockets.append(sock)
                sock.bind(('0.0.0.0', 7400+250*domain+offset))
            with tempfile.TemporaryDirectory() as directory:
                output = Path(directory)/'probe.json'
                result = subprocess.run([sys.executable, str(PROBE), '--output', str(output), '--timeout', '1'],
                    env=dict(os.environ, ROS_DOMAIN_ID=str(domain), ROS_LOCALHOST_ONLY='1',
                             CYCLONEDDS_URI=config, RMW_IMPLEMENTATION='rmw_cyclonedds_cpp'),
                    capture_output=True, text=True, timeout=10)
                self.assertNotEqual(result.returncode, 0)
                self.assertIn('Failed to find a free participant index', result.stderr)
                evidence = json.loads(output.read_text())
                self.assertEqual(evidence['status'], 'FAIL')
                self.assertFalse(evidence['participant_created'])
        finally:
            for sock in sockets:
                sock.close()

    def test_empty_graph_is_not_a_pass_even_when_participant_is_created(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'probe.json'
            result = subprocess.run([sys.executable, str(PROBE), '--output', str(output), '--timeout', '0.3'],
                                    capture_output=True, text=True, timeout=10)
            evidence = json.loads(output.read_text())
            self.assertNotEqual(result.returncode, 0)
            self.assertTrue(evidence['participant_created'])
            self.assertEqual(evidence['status'], 'FAIL')


if __name__ == '__main__':
    unittest.main()
