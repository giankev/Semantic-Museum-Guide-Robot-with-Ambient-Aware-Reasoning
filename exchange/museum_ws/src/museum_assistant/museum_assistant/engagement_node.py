"""ROS adapter for sensor-only social availability estimation."""

import json
import math
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
import cv2
from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image, LaserScan
from std_msgs.msg import String
from museum_assistant.engagement import EngagementModel, frontal_lidar_candidate
from museum_assistant.person_detector import PersonDetector


class EngagementNode(Node):
    def __init__(self):
        super().__init__("engagement_node")
        defaults = {
            "model_path": "", "person_confidence_threshold": 0.35,
            "central_image_fraction": 0.7, "frontal_half_angle_deg": 35.0,
            "max_engagement_distance_m": 2.0,
            "max_stationary_speed_mps": 0.25, "inference_rate_hz": 5.0,
            "publish_debug_image": False,
        }
        for name, value in defaults.items():
            self.declare_parameter(name, value)
        values = {name: self.get_parameter(name).value for name in defaults}
        model_path = str(values["model_path"])
        if not model_path:
            model_path = str(Path(get_package_share_directory("museum_assistant"))
                             / "models" / "object_detection_nanodet_2022nov.onnx")
        self.central_fraction = float(values["central_image_fraction"])
        self.half_angle = math.radians(float(values["frontal_half_angle_deg"]))
        self.period = 1.0 / float(values["inference_rate_hz"])
        self.publish_debug = bool(values["publish_debug_image"])
        self.detector = PersonDetector(model_path,
                                       float(values["person_confidence_threshold"]),
                                       self.central_fraction)
        self.model = EngagementModel(
            float(values["max_engagement_distance_m"]),
            float(values["max_stationary_speed_mps"]),
        )
        self.bridge = CvBridge()
        self.distance = self.bearing = self.last_inference = None
        self.state_publisher = self.create_publisher(
            String, "/museum/engagement_state", 10)
        self.debug_publisher = self.create_publisher(
            Image, "/museum/engagement_debug_image", 1)
        self.create_subscription(Image, "/head_front_camera/rgb/image_raw",
                                 self._image_callback, qos_profile_sensor_data)
        self.create_subscription(LaserScan, "/scan_raw", self._scan_callback,
                                 qos_profile_sensor_data)
        self.get_logger().info(
            "Estimating interaction availability from RGB, LiDAR, and timing")

    def _scan_callback(self, message):
        self.distance, self.bearing = frontal_lidar_candidate(
            message.ranges, message.angle_min, message.angle_increment,
            message.range_min, message.range_max, self.half_angle)

    def _image_callback(self, message):
        now = self.get_clock().now().nanoseconds / 1e9
        if self.last_inference is not None and now - self.last_inference < self.period:
            return
        self.last_inference = now
        image = self.bridge.imgmsg_to_cv2(message, "bgr8")
        detection = self.detector.detect(image)
        central = (detection.detected
                   and abs(detection.center_x_normalized - 0.5)
                   <= self.central_fraction / 2)
        result = self.model.update(now=now, visual_person=detection.detected,
                                   central=central, distance_m=self.distance)
        payload = {
            "state": result.state.value.lower(),
            "person_detected": detection.detected,
            "person_confidence": detection.confidence,
            "bbox_center_x": detection.center_x_normalized,
            "distance_m": self.distance, "bearing_rad": self.bearing,
            "radial_speed_mps": result.radial_speed_mps,
            "dwell_s": result.dwell_s,
        }
        output = String(data=json.dumps(payload))
        self.state_publisher.publish(output)
        if self.publish_debug:
            self._publish_debug(message, image, detection, result.state.value)

    def _publish_debug(self, source, image, detection, state):
        debug = image.copy()
        if detection.detected:
            corner = (detection.bbox_x + detection.bbox_width,
                      detection.bbox_y + detection.bbox_height)
            cv2.rectangle(debug, (detection.bbox_x, detection.bbox_y),
                          corner, (0, 255, 0), 2)
            cv2.putText(debug, f"person {detection.confidence:.2f}",
                        (10, 30), 0, 0.7, (0, 255, 0), 2)
        distance = "n/a" if self.distance is None else f"{self.distance:.2f}m"
        cv2.putText(debug, f"{state} d={distance}", (10, 60), 0, 0.7,
                    (0, 255, 255), 2)
        output = self.bridge.cv2_to_imgmsg(debug, "bgr8")
        output.header = source.header
        self.debug_publisher.publish(output)


def main(args=None):
    rclpy.init(args=args)
    node = EngagementNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
