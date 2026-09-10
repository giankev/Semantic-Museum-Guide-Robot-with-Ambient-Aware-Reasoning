#!/usr/bin/env python3
"""Read-only exact piecewise comfort contours for the accepted critic."""
import math
import rclpy
from geometry_msgs.msg import Point
from visualization_msgs.msg import Marker, MarkerArray
from museum_assistant.social_visualization_node import SocialVisualizationNode, _marker, _color


class Contours(SocialVisualizationNode):
    def _zone_marker(self, msg, person, index, moving):
        if self.parameters is None:
            return None
        marker = _marker(msg, 'social_zones', index, Marker.LINE_STRIP)
        marker.pose.orientation.w = 1.0
        marker.scale.x = 0.035
        _color(marker, 1.0 if moving else 0.1, 0.65, 0.2 if moving else 1.0, 0.8)
        radius = self.parameters[1]
        heading = math.atan2(person.velocity.y, person.velocity.x) if moving else 0.0
        c, s = math.cos(heading), math.sin(heading)
        for i in range(97):
            angle = 2 * math.pi * i / 96
            longitudinal = math.cos(angle)
            front, side, rear = self.parameters[4:7] if moving else (1.0, 1.0, 1.0)
            x = radius * longitudinal * (front if longitudinal >= 0 else rear)
            y = radius * math.sin(angle) * side
            marker.points.append(Point(x=person.pose.x+c*x-s*y,
                                       y=person.pose.y+s*x+c*y, z=0.04))
        return marker

    def _people_cb(self, msg):
        output = MarkerArray()
        output.markers.append(Marker(action=Marker.DELETEALL))
        for i, person in enumerate(msg.pedestrians):
            if person.identifier == 'visitor_1':
                continue
            moving = self._is_anisotropic(math.hypot(person.velocity.x, person.velocity.y))
            markers = [self._position_marker(msg, person, i, moving),
                       self._text_marker(msg, person, i), self._zone_marker(msg, person, i, moving)]
            for marker in markers:
                if marker is not None:
                    marker.lifetime.sec = 1
                    output.markers.append(marker)
        self.marker_publisher.publish(output)


def main():
    rclpy.init()
    node = Contours()
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
