// Read-only attribution for Humble versions whose rclpy drops publisher GIDs.
#include <chrono>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <tuple>
#include <rclcpp/rclcpp.hpp>
#include <tf2_msgs/msg/tf_message.hpp>

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  auto node = std::make_shared<rclcpp::Node>("video1_tf_authority_audit");
  using Key = std::tuple<std::string, std::string, std::string>;
  std::map<Key, std::size_t> edges;
  auto callback = [&edges](const tf2_msgs::msg::TFMessage::SharedPtr msg,
      const rclcpp::MessageInfo & info) {
      std::ostringstream gid;
      for (auto byte : info.get_rmw_message_info().publisher_gid.data) {
        gid << std::hex << std::setfill('0') << std::setw(2) << static_cast<unsigned>(byte);
      }
      for (const auto & tf : msg->transforms) {
        ++edges[{tf.header.frame_id, tf.child_frame_id, gid.str()}];
      }
    };
  auto dynamic = node->create_subscription<tf2_msgs::msg::TFMessage>(
    "/tf", rclcpp::SensorDataQoS(), callback);
  auto fixed = node->create_subscription<tf2_msgs::msg::TFMessage>(
    "/tf_static", rclcpp::QoS(100).transient_local().reliable(), callback);
  const auto duration = node->declare_parameter("duration_seconds", 15.0);
  if (duration <= 0 || duration > 600) {return 2;}
  auto timer = node->create_wall_timer(std::chrono::duration<double>(duration), [&]() {
      for (const auto & [key, count] : edges) {
        const auto & [parent, child, gid] = key;
        std::cout << "{\"kind\":\"edge\",\"parent\":" << std::quoted(parent)
          << ",\"child\":" << std::quoted(child) << ",\"gid\":" << std::quoted(gid)
          << ",\"samples\":" << count << "}\n";
      }
      for (const auto & topic : {"/tf", "/tf_static"}) {
        for (const auto & publisher : node->get_publishers_info_by_topic(topic)) {
          std::ostringstream gid;
          for (auto byte : publisher.endpoint_gid()) {
            gid << std::hex << std::setfill('0') << std::setw(2) << static_cast<unsigned>(byte);
          }
          std::cout << "{\"kind\":\"publisher\",\"topic\":" << std::quoted(topic)
            << ",\"node\":" << std::quoted(publisher.node_namespace() + publisher.node_name())
            << ",\"gid\":" << std::quoted(gid.str()) << "}\n";
        }
      }
      std::cout.flush();
      rclcpp::shutdown();
    });
  rclcpp::spin(node);
  return edges.empty() ? 1 : 0;
}
