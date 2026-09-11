// Exercise the installed Humble BT action client against real DDS actions.
// Deliberately delayed acknowledgements reproduce the GUI-load failure without
// sending any goal to the robot or depending on Gazebo scheduling.
#include <chrono>
#include <iostream>
#include <thread>
#include "nav2_behavior_tree/bt_action_node.hpp"
#include "nav2_msgs/action/follow_path.hpp"

using namespace std::chrono_literals;
using Action = nav2_msgs::action::FollowPath;

bool trial(int timeout_ms, BT::NodeStatus expected)
{
  auto server_node = std::make_shared<rclcpp::Node>("audit_ack_server");
  auto client_node = std::make_shared<rclcpp::Node>("audit_ack_client");
  auto server = rclcpp_action::create_server<Action>(
    server_node, "/museum_audit_delayed_ack",
    [](const auto &, const auto &) {
      std::this_thread::sleep_for(75ms);
      return rclcpp_action::GoalResponse::ACCEPT_AND_EXECUTE;
    },
    [](const auto &) {return rclcpp_action::CancelResponse::ACCEPT;},
    [](const auto & handle) {
      std::this_thread::sleep_for(75ms);
      handle->succeed(std::make_shared<Action::Result>());
    });
  rclcpp::executors::SingleThreadedExecutor executor;
  executor.add_node(server_node);
  std::thread spin([&]() {executor.spin();});
  bool passed = false;
  try {
    BT::NodeConfiguration config;
    config.blackboard = BT::Blackboard::create();
    config.blackboard->set("node", client_node);
    config.blackboard->set("bt_loop_duration", 100ms);
    config.blackboard->set("server_timeout", std::chrono::milliseconds(timeout_ms));
    config.blackboard->set("wait_for_service_timeout", 3000ms);
    nav2_behavior_tree::BtActionNode<Action> action(
      "AuditFollowPath", "/museum_audit_delayed_ack", config);
    auto status = BT::NodeStatus::RUNNING;
    const auto deadline = std::chrono::steady_clock::now() + 3s;
    while (status == BT::NodeStatus::RUNNING && std::chrono::steady_clock::now() < deadline) {
      status = action.executeTick();
      std::this_thread::sleep_for(10ms);
    }
    passed = status == expected;
    std::cout << "ack timeout=" << timeout_ms << "ms, status=" << static_cast<int>(status)
              << ", expected=" << static_cast<int>(expected) << std::endl;
    // Let the server finish even in the intentionally timed-out case.
    std::this_thread::sleep_for(200ms);
  } catch (const std::exception & error) {
    std::cerr << error.what() << std::endl;
  }
  executor.cancel();
  spin.join();
  return passed;
}

int main(int argc, char ** argv)
{
  rclcpp::init(argc, argv);
  bool passed = true;
  for (int repeat = 0; repeat < 3; ++repeat) {
    passed = trial(20, BT::NodeStatus::FAILURE) && passed;
    passed = trial(200, BT::NodeStatus::SUCCESS) && passed;
  }
  rclcpp::shutdown();
  return passed ? 0 : 1;
}
