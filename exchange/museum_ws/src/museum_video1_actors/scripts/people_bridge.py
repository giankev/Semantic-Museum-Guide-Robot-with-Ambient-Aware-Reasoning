#!/usr/bin/env python3
"""Publish observed actors in odom using the existing odometry's exact alignment."""
from collections import OrderedDict
from copy import deepcopy
import math
import rclpy
from rclpy.node import Node
from nav_msgs.msg import Odometry
from social_nav_msgs.msg import Pedestrians
from demo_math import alignment, rotate, transform, wrap, yaw


class Bridge(Node):
    def __init__(self):
        super().__init__('video1_people_bridge')
        self.pairs = [OrderedDict(), OrderedDict()]
        self.frame = None
        count = self.declare_parameter('actor_count', 1).value
        if not isinstance(count, int) or not 1 <= count <= 8:
            raise ValueError('actor_count must be in 1..8')
        self.expected = {f'walker_{i}' for i in range(1, count+1)}
        self.samples = OrderedDict()
        self.last_published = None
        self.raw_pub = self.create_publisher(Pedestrians, '/museum/video1/actor_states', 10)
        self.pub = self.create_publisher(Pedestrians, '/people', 10)
        self.odom_subscriptions = [
            self.create_subscription(Odometry, '/ground_truth_odom', lambda m: self.odom(0, m), 20),
            self.create_subscription(Odometry, '/museum/ground_truth_odom', lambda m: self.odom(1, m), 20)]
        self.create_subscription(Pedestrians, '/museum/video1/actor_samples', self.sample, 80)

    def odom(self, side, msg):
        if self.frame is not None:
            return
        key = (msg.header.stamp.sec, msg.header.stamp.nanosec)
        p = msg.pose.pose
        self.pairs[side][key] = (p.position.x, p.position.y, yaw(p.orientation))
        while len(self.pairs[side]) > 100:
            self.pairs[side].popitem(last=False)
        if key not in self.pairs[1-side]:
            return
        self.frame = alignment(self.pairs[0][key], self.pairs[1][key])
        self.pairs = [OrderedDict(), OrderedDict()]
        self.get_logger().info(f'Observed world->odom alignment: {self.frame}')
        for sub in self.odom_subscriptions:
            self.destroy_subscription(sub)
        self.odom_subscriptions.clear()

    def sample(self, msg):
        if msg.header.frame_id != 'world' or len(msg.pedestrians) != 1:
            self.get_logger().error('Invalid individual Actor sample; withholding frame')
            return
        p = msg.pedestrians[0]
        key = (msg.header.stamp.sec, msg.header.stamp.nanosec)
        if p.identifier not in self.expected or key <= (0, 0) or not all(math.isfinite(v) for v in
                (p.pose.x, p.pose.y, p.pose.theta, p.velocity.x, p.velocity.y)):
            self.get_logger().error('Invalid Actor state; withholding frame')
            return
        if self.last_published is not None and key <= self.last_published:
            return
        frame = self.samples.setdefault(key, {})
        frame[p.identifier] = p
        while len(self.samples) > 5:
            self.samples.popitem(last=False)
        if set(frame) != self.expected:
            return
        combined = Pedestrians()
        combined.header = msg.header
        combined.pedestrians = [frame[name] for name in sorted(self.expected)]
        self.last_published = key
        self.raw_pub.publish(combined)
        self.people(combined)
        self.samples.pop(key, None)

    def people(self, msg):
        if self.frame is None:
            return
        output = deepcopy(msg)
        output.header.frame_id = 'odom'
        for p in output.pedestrians:
            if not all(math.isfinite(v) for v in
                       (p.pose.x, p.pose.y, p.pose.theta, p.velocity.x, p.velocity.y)):
                self.get_logger().error('Invalid actor state; withholding /people')
                return
            p.pose.x, p.pose.y = transform(p.pose.x, p.pose.y, self.frame)
            p.pose.theta = wrap(p.pose.theta + self.frame[2])
            p.velocity.x, p.velocity.y = rotate(p.velocity.x, p.velocity.y, self.frame[2])
        # Preserve physics timestamp. A failed actor never gets fresh invented data.
        self.pub.publish(output)


def main():
    rclpy.init()
    node = Bridge()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()
