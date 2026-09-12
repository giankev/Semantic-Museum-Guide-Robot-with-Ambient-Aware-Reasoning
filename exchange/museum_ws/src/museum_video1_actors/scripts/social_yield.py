#!/usr/bin/env python3
"""Scale Nav2's smoothed velocity for social yielding without touching its goal."""
import json
import math
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from geometry_msgs.msg import Twist
from nav_msgs.msg import Odometry
from social_nav_msgs.msg import Pedestrians
from std_msgs.msg import String
from demo_math import yaw, stamp_seconds
from social_yield_math import YieldPolicy


class SocialYield(Node):
    def __init__(self):
        super().__init__('social_yield')
        defaults = dict(corridor_half_width=.65, slow_distance=2.5, stop_distance=1.3,
                        release_distance=1.65, release_half_width=.85, prediction_horizon=2.,
                        stop_horizon=1.2, clear_time=.8, input_timeout=.4)
        config = {k: float(self.declare_parameter(k, v).value) for k, v in defaults.items()}
        if not all(math.isfinite(v) and v > 0 for v in config.values()) or not (
            config['stop_distance'] < config['release_distance'] < config['slow_distance'] and
            config['corridor_half_width'] < config['release_half_width']):
            raise ValueError('Invalid social-yield configuration')
        self.policy, self.timeout = YieldPolicy(config), config['input_timeout']
        self.people = self.odom = self.command = None
        self.command_time = None
        self.last_state = None
        self.output = self.create_publisher(Twist, '/cmd_vel', 10)
        self.status = self.create_publisher(String, '/museum/social_yield/status', 10)
        self.create_subscription(Pedestrians, '/people', lambda m: setattr(self, 'people', m), qos_profile_sensor_data)
        self.create_subscription(Odometry, '/museum/ground_truth_odom', lambda m: setattr(self, 'odom', m), qos_profile_sensor_data)
        self.create_subscription(Twist, '/museum/nav_cmd_vel', self.on_command, 10)
        self.create_timer(.05, self.tick)

    def now(self):
        return self.get_clock().now().nanoseconds/1e9

    def on_command(self, msg):
        self.command, self.command_time = msg, self.now()

    def tick(self):
        now = self.now()
        result = dict(state='WAITING_FOR_INPUT', scale=0., nearest_person=None, distance=None)
        output = Twist()
        error = None
        try:
            fresh = (now > 0 and self.people is not None and self.odom is not None and
                     self.people.header.frame_id == self.odom.header.frame_id == 'odom' and
                     all(-.1 <= now-stamp_seconds(m.header.stamp) <= self.timeout
                         for m in (self.people, self.odom)))
            if fresh:
                robot, angle = self.odom.pose.pose.position, yaw(self.odom.pose.pose.orientation)
                c, s = math.cos(angle), math.sin(angle)
                people = []
                for p in self.people.pedestrians:
                    age = max(0., now-stamp_seconds(self.people.header.stamp))
                    dx, dy = p.pose.x+p.velocity.x*age-robot.x, p.pose.y+p.velocity.y*age-robot.y
                    people.append((p.identifier, c*dx+s*dy, -s*dx+c*dy,
                                   c*p.velocity.x+s*p.velocity.y, -s*p.velocity.x+c*p.velocity.y))
                result = self.policy.update(now, people, self.odom.twist.twist.linear.x)
                if self.command_time is not None and 0 <= now-self.command_time <= self.timeout:
                    values = (self.command.linear.x, self.command.angular.z)
                    if not all(math.isfinite(v) for v in values):
                        raise ValueError('Invalid Nav2 velocity')
                    output.linear.x = self.command.linear.x*result['scale']
                    output.angular.z = self.command.angular.z*result['scale']
            elif self.last_state not in (None, 'WAITING_FOR_INPUT'):
                result['state'] = 'STALE_INPUT'
        except Exception as exc:
            result.update(state='INVALID_INPUT', scale=0.)
            error = str(exc)
        self.output.publish(output)
        result.update(t=now, input_vx=self.command.linear.x if self.command else None,
                      output_vx=output.linear.x, robot_vx=self.odom.twist.twist.linear.x if self.odom else None,
                      error=error)
        result = {k: (None if isinstance(v, float) and not math.isfinite(v) else v) for k, v in result.items()}
        self.status.publish(String(data=json.dumps(result, allow_nan=False)))
        if result['state'] != self.last_state:
            self.get_logger().info('SOCIAL STATE: '+result['state'])
            self.last_state = result['state']


def main():
    rclpy.init()
    node = SocialYield()
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
