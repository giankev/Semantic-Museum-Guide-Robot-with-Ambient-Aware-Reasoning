import json
import time

import rclpy
from rclpy.executors import SingleThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, LaserScan
from std_msgs.msg import String

from museum_assistant.engagement import EngagementModel
import museum_assistant.engagement_node as engagement_node_module
from museum_assistant.person_detector import PersonDetection
from museum_assistant.visitor_session_node import VisitorSessionNode


class FakeDetector:
    visible = False

    def __init__(self, *_args):
        pass

    def detect(self, _image):
        if not self.visible:
            return PersonDetection()
        return PersonDetection(
            True, 0.8, 0, 0, 1, 1, 0.5, 0.5, 1.0
        )


def spin_until(executor, predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        executor.spin_once(timeout_sec=0.05)
        if predicate():
            return
    raise AssertionError("Timed out waiting for ROS-light engagement output")


def test_ros_topics_and_engagement_gated_session(monkeypatch):
    real_model = EngagementModel
    monkeypatch.setattr(engagement_node_module, "PersonDetector", FakeDetector)
    monkeypatch.setattr(
        engagement_node_module,
        "EngagementModel",
        lambda distance, speed: real_model(
            distance, speed, potential_dwell_s=0.0, engaged_dwell_s=0.01
        ),
    )
    rclpy.init(args=["--ros-args", "-p", "require_engagement:=true"])
    engagement = engagement_node_module.EngagementNode()
    engagement.period = 0.0
    session = VisitorSessionNode()
    harness = Node("engagement_ros_light_harness")
    images = harness.create_publisher(
        Image, "/head_front_camera/rgb/image_raw", qos_profile_sensor_data
    )
    scans = harness.create_publisher(
        LaserScan, "/scan_raw", qos_profile_sensor_data
    )
    states, sessions = [], []
    harness.create_subscription(
        String, "/museum/engagement_state",
        lambda message: states.append(json.loads(message.data)), 10
    )
    harness.create_subscription(
        String, "/museum/session_state",
        lambda message: sessions.append(json.loads(message.data)), 10
    )
    executor = SingleThreadedExecutor()
    for node in (engagement, session, harness):
        executor.add_node(node)
    image = Image(height=1, width=1, encoding="bgr8", step=3,
                  data=[0, 0, 0])
    scan = LaserScan(
        angle_min=-0.5, angle_max=0.5, angle_increment=0.1,
        range_min=0.05, range_max=25.0, ranges=[1.5] * 11
    )
    try:
        scans.publish(scan)
        images.publish(image)
        spin_until(
            executor, lambda: states and states[-1]["state"] == "no_person"
        )
        assert not sessions
        FakeDetector.visible = True
        images.publish(image)
        spin_until(
            executor,
            lambda: states and states[-1]["state"] == "potential_interaction",
        )
        assert not sessions
        time.sleep(0.02)
        images.publish(image)
        spin_until(
            executor, lambda: states and states[-1]["state"] == "engaged"
        )
        spin_until(executor, lambda: bool(sessions))
        assert sessions[-1] == {
            "session_id": "session_1",
            "track_id": "visitor_1",
            "state": "active",
        }
    finally:
        FakeDetector.visible = False
        for node in (engagement, session, harness):
            executor.remove_node(node)
            node.destroy_node()
        executor.shutdown()
        rclpy.shutdown()
