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
        self.pub = self.create_publisher(Pedestrians, '/people', 10)
        self.create_subscription(Odometry, '/ground_truth_odom', lambda m: self.odom(0, m), 20)
        self.create_subscription(Odometry, '/museum/ground_truth_odom', lambda m: self.odom(1, m), 20)
        self.create_subscription(Pedestrians, '/museum/video1/actor_states', self.people, 10)

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

    def people(self, msg):
        if self.frame is None or msg.header.frame_id != 'world':
            return
        if len(msg.pedestrians) != 1 or msg.pedestrians[0].identifier != 'walker_1':
            self.get_logger().error('Unexpected actor set; one-actor POC only')
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
