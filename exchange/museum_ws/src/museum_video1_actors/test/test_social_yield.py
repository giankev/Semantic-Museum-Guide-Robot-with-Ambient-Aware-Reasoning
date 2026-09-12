"""Deterministic behavior tests plus real Humble bridge and velocity interfaces."""
import json
import os
import math
from pathlib import Path
import sys
import unittest
from unittest.mock import patch
import yaml

PACKAGE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE/'scripts'))
from social_yield_math import YieldPolicy
import rclpy
from rclpy.parameter import Parameter
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from social_nav_msgs.msg import Pedestrian, Pedestrians
from people_bridge import Bridge
from social_yield import SocialYield

CONFIG = yaml.safe_load((PACKAGE/'config/social_yield.yaml').read_text())['social_yield']['ros__parameters']


class PolicyTests(unittest.TestCase):
    def test_ros_entrypoint_is_executable(self):
        self.assertTrue(os.access(PACKAGE/'scripts/social_yield.py', os.X_OK))

    def test_far_behind_slow_stop_and_hysteretic_resume(self):
        policy = YieldPolicy(CONFIG)
        self.assertEqual(policy.update(1., [('p', -.3, 0., 0., 0.)], .2)['state'], 'CLEAR')
        self.assertEqual(policy.update(2., [('p', 4., 0., 0., 0.)], .2)['scale'], 1.)
        self.assertEqual(policy.update(3., [('p', 2., 0., 0., 0.)], .2)['state'], 'SLOW')
        self.assertEqual(policy.update(4., [('p', 1.2, 0., 0., 0.)], .2)['state'], 'YIELDING')
        # Merely crossing the entry threshold must not release the stop.
        self.assertEqual(policy.update(4.1, [('p', 1.75, 0., 0., 0.)], .0)['state'], 'YIELDING')
        self.assertEqual(policy.update(5., [], .0)['state'], 'YIELDING')
        self.assertEqual(policy.update(5.7, [], .0)['state'], 'YIELDING')
        self.assertEqual(policy.update(5.9, [], .0)['state'], 'CLEAR')

    def test_incoming_crossing_is_distinct_from_person_moving_away(self):
        incoming = YieldPolicy(CONFIG).update(1., [('p', 1.3, 1., 0., -.4)], .2)
        leaving = YieldPolicy(CONFIG).update(1., [('p', 1.3, 1., 0., .4)], .2)
        self.assertEqual(incoming['state'], 'YIELDING')
        self.assertEqual(leaving['state'], 'CLEAR')

    def test_nonfinite_person_is_rejected(self):
        with self.assertRaises(ValueError):
            YieldPolicy(CONFIG).update(1., [('p', math.nan, 0., 0., 0.)], .2)


class RosTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rclpy.init(args=["--ros-args", "-p", "actor_count:=3"])

    @classmethod
    def tearDownClass(cls):
        rclpy.shutdown()

    def test_bridge_requires_complete_same_stamp_actor_set(self):
        # Real rclpy Node and generated messages, without a Gazebo dependency.
        node = Bridge()
        try:
            node.frame = (2., -1., math.pi/2)
            def sample(identifier, stamp):
                msg = Pedestrians()
                msg.header.frame_id = 'world'
                msg.header.stamp.sec = stamp
                person = Pedestrian()
                person.identifier, person.pose.x, person.velocity.x = identifier, 1., .2
                msg.pedestrians = [person]
                return msg
            with patch.object(node.pub, 'publish') as output, patch.object(node.raw_pub, 'publish'):
                node.sample(sample('walker_1', 1))
                node.sample(sample('walker_2', 2))
                node.sample(sample('walker_3', 1))
                output.assert_not_called()
                node.sample(sample('walker_2', 1))
                self.assertEqual(output.call_count, 1)
                msg = output.call_args.args[0]
                self.assertEqual(len(msg.pedestrians), 3)
                self.assertEqual(msg.header.frame_id, 'odom')
                self.assertAlmostEqual(msg.pedestrians[0].velocity.x, 0.)
                self.assertAlmostEqual(msg.pedestrians[0].velocity.y, .2)
                self.assertAlmostEqual(msg.pedestrians[0].pose.x, 2.)
                node.sample(sample('walker_2', 1))
                self.assertEqual(output.call_count, 1)
        finally:
            node.destroy_node()

    def test_velocity_filter_stops_and_handles_stale_or_invalid_commands(self):
        node = SocialYield()
        try:
            node.odom = Odometry()
            node.odom.header.frame_id = 'odom'
            node.odom.header.stamp.sec = 1
            node.odom.pose.pose.orientation.w = 1.
            node.people = Pedestrians()
            node.people.header.frame_id = 'odom'
            node.people.header.stamp.sec = 1
            p = Pedestrian()
            p.identifier, p.pose.x = 'walker_1', 1.
            node.people.pedestrians = [p]
            with patch.object(node, 'now', return_value=1.), patch.object(node.output, 'publish') as pub, patch.object(node.status, 'publish') as status:
                command = Twist()
                command.linear.x = .2
                node.on_command(command)
                node.tick()
                self.assertEqual(pub.call_args.args[0].linear.x, 0.)
                self.assertEqual(json.loads(status.call_args.args[0].data)['state'], 'YIELDING')
                command.linear.x = math.nan
                node.tick()
                self.assertEqual(pub.call_args.args[0].linear.x, 0.)
                self.assertEqual(json.loads(status.call_args.args[0].data)['state'], 'INVALID_INPUT')
            with patch.object(node, 'now', return_value=3.), patch.object(node.output, 'publish') as pub:
                node.tick()
                self.assertEqual(pub.call_args.args[0].linear.x, 0.)
        finally:
            node.destroy_node()


if __name__ == '__main__':
    unittest.main()
