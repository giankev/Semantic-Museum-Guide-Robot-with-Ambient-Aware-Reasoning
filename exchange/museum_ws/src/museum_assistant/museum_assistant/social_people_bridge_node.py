"""Bridge the public people stream to the legacy SocialLayer input type."""

import rclpy
from people_msgs.msg import People, Person
from rclpy.node import Node
from social_nav_msgs.msg import Pedestrians

from museum_assistant.social_people_bridge import compatibility_people_fields


class SocialPeopleBridgeNode(Node):
    def __init__(self):
        super().__init__("social_people_bridge_node")
        self._publisher = self.create_publisher(People, "/people_nav2", 10)
        self._subscription = self.create_subscription(
            Pedestrians,
            "/people",
            self._handle_people,
            10,
        )
        self.get_logger().info(
            "Bridging /people to people_msgs/People on /people_nav2"
        )

    def _handle_people(self, msg: Pedestrians) -> None:
        fields = compatibility_people_fields(
            frame_id=msg.header.frame_id,
            stamp_sec=msg.header.stamp.sec,
            stamp_nanosec=msg.header.stamp.nanosec,
            pedestrians=(
                (
                    pedestrian.identifier,
                    pedestrian.pose.x,
                    pedestrian.pose.y,
                    pedestrian.velocity.x,
                    pedestrian.velocity.y,
                )
                for pedestrian in msg.pedestrians
            ),
        )

        output = People()
        output.header.stamp.sec = fields.stamp_sec
        output.header.stamp.nanosec = fields.stamp_nanosec
        output.header.frame_id = fields.frame_id
        for item in fields.people:
            person = Person()
            person.name = item.name
            person.position.x = item.x
            person.position.y = item.y
            person.velocity.x = item.vx
            person.velocity.y = item.vy
            person.reliability = item.reliability
            output.people.append(person)
        self._publisher.publish(output)


def main(args=None):
    rclpy.init(args=args)
    node = SocialPeopleBridgeNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
