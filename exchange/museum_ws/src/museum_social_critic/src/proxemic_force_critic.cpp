#include "museum_social_critic/proxemic_force_critic.hpp"

#include <algorithm>
#include <cmath>
#include <functional>
#include <stdexcept>
#include <utility>

#include "geometry_msgs/msg/point_stamped.hpp"
#include "geometry_msgs/msg/vector3_stamped.hpp"
#include "nav2_util/node_utils.hpp"
#include "pluginlib/class_list_macros.hpp"
#include "tf2_geometry_msgs/tf2_geometry_msgs.hpp"

namespace museum_social_critic
{

double proxemicCost(double distance, double comfort_distance, double sigma)
{
  if (!std::isfinite(distance) || distance < 0.0 ||
    !std::isfinite(comfort_distance) || comfort_distance <= 0.0 ||
    !std::isfinite(sigma) || sigma <= 0.0)
  {
    throw std::invalid_argument("Proxemic cost inputs must be finite and positive.");
  }

  const double exponent = (distance - comfort_distance) / sigma;
  if (exponent >= 0.0) {
    const double decay = std::exp(-exponent);
    return decay / (1.0 + decay);
  }
  const double growth = std::exp(exponent);
  return 1.0 / (1.0 + growth);
}

double maximumProxemicScore(
  const std::vector<TimedPoint> & robot_poses,
  const std::vector<PersonState> & people,
  const std::unordered_set<std::string> & ignored_identifiers,
  double comfort_distance,
  double sigma)
{
  double maximum = 0.0;
  for (const auto & person : people) {
    if (ignored_identifiers.count(person.identifier) != 0U) {
      continue;
    }
    for (const auto & robot : robot_poses) {
      const double person_x = person.x + person.vx * robot.time;
      const double person_y = person.y + person.vy * robot.time;
      const double distance = std::hypot(robot.x - person_x, robot.y - person_y);
      maximum = std::max(maximum, proxemicCost(distance, comfort_distance, sigma));
    }
  }
  return maximum;
}

void ProxemicForceCritic::onInit()
{
  auto node = node_.lock();
  if (!node) {
    throw std::runtime_error("ProxemicForceCritic could not lock its lifecycle node.");
  }

  logger_ = node->get_logger();
  clock_ = node->get_clock();
  const std::string prefix = dwb_plugin_name_ + "." + name_;
  nav2_util::declare_parameter_if_not_declared(
    node, prefix + ".comfort_distance", rclcpp::ParameterValue(1.0));
  nav2_util::declare_parameter_if_not_declared(
    node, prefix + ".sigma", rclcpp::ParameterValue(0.4));
  nav2_util::declare_parameter_if_not_declared(
    node, prefix + ".people_topic", rclcpp::ParameterValue(std::string("/people")));
  nav2_util::declare_parameter_if_not_declared(
    node, prefix + ".people_timeout", rclcpp::ParameterValue(1.0));
  nav2_util::declare_parameter_if_not_declared(
    node, prefix + ".ignored_identifiers",
    rclcpp::ParameterValue(std::vector<std::string>{"visitor_1"}));

  std::vector<std::string> ignored;
  node->get_parameter(prefix + ".comfort_distance", comfort_distance_);
  node->get_parameter(prefix + ".sigma", sigma_);
  node->get_parameter(prefix + ".people_topic", people_topic_);
  node->get_parameter(prefix + ".people_timeout", people_timeout_);
  node->get_parameter(prefix + ".ignored_identifiers", ignored);

  if (!std::isfinite(comfort_distance_) || comfort_distance_ <= 0.0 ||
    !std::isfinite(sigma_) || sigma_ <= 0.0 ||
    !std::isfinite(people_timeout_) || people_timeout_ <= 0.0 ||
    people_topic_.empty())
  {
    throw std::invalid_argument("ProxemicForceCritic parameters are invalid.");
  }
  ignored_identifiers_.insert(ignored.begin(), ignored.end());

  people_subscription_ = node->create_subscription<social_nav_msgs::msg::Pedestrians>(
    people_topic_, rclcpp::QoS(10),
    std::bind(&ProxemicForceCritic::peopleCallback, this, std::placeholders::_1));

  RCLCPP_INFO(
    logger_,
    "ProxemicForceCritic subscribed to %s; frame target=%s; ignored identifiers=%zu",
    people_topic_.c_str(), costmap_ros_->getGlobalFrameID().c_str(),
    ignored_identifiers_.size());
}

void ProxemicForceCritic::peopleCallback(
  const social_nav_msgs::msg::Pedestrians::SharedPtr message)
{
  {
    std::lock_guard<std::mutex> lock(people_mutex_);
    latest_people_ = message;
  }

  if (!logged_snapshot_) {
    std::size_t ignored = 0;
    for (const auto & person : message->pedestrians) {
      ignored += ignored_identifiers_.count(person.identifier) != 0U ? 1U : 0U;
    }
    RCLCPP_INFO(
      logger_, "Received %zu pedestrians on %s: considered=%zu ignored=%zu",
      message->pedestrians.size(), people_topic_.c_str(),
      message->pedestrians.size() - ignored, ignored);
    logged_snapshot_ = true;
  }
}

bool ProxemicForceCritic::prepare(
  const geometry_msgs::msg::Pose2D &,
  const nav_2d_msgs::msg::Twist2D &,
  const geometry_msgs::msg::Pose2D &,
  const nav_2d_msgs::msg::Path2D &)
{
  social_nav_msgs::msg::Pedestrians::SharedPtr snapshot;
  {
    std::lock_guard<std::mutex> lock(people_mutex_);
    snapshot = latest_people_;
  }

  prepared_people_.clear();
  cycle_min_score_ = std::numeric_limits<double>::infinity();
  cycle_max_score_ = 0.0;
  if (!snapshot) {
    return true;
  }

  const rclcpp::Time stamp(snapshot->header.stamp);
  const double age = (clock_->now() - stamp).seconds();
  if (!std::isfinite(age) || age > people_timeout_) {
    RCLCPP_WARN_THROTTLE(
      logger_, *clock_, 5000,
      "Ignoring stale people snapshot (age %.3f s, timeout %.3f s)",
      age, people_timeout_);
    return true;
  }

  const std::string source_frame = snapshot->header.frame_id;
  const std::string target_frame = costmap_ros_->getGlobalFrameID();
  if (source_frame.empty()) {
    RCLCPP_WARN_THROTTLE(
      logger_, *clock_, 5000,
      "People snapshot has no frame; social score is zero for this cycle");
    return true;
  }

  geometry_msgs::msg::TransformStamped transform;
  const bool needs_transform = source_frame != target_frame;
  if (needs_transform) {
    try {
      transform = costmap_ros_->getTfBuffer()->lookupTransform(
        target_frame, source_frame, stamp, rclcpp::Duration::from_seconds(0.05));
    } catch (const tf2::TransformException & error) {
      RCLCPP_WARN_THROTTLE(
        logger_, *clock_, 5000,
        "Cannot transform people from %s to %s: %s; social score is zero for this cycle",
        source_frame.c_str(), target_frame.c_str(), error.what());
      return true;
    }
  }

  for (const auto & person : snapshot->pedestrians) {
    if (ignored_identifiers_.count(person.identifier) != 0U) {
      continue;
    }

    PersonState prepared{
      person.identifier,
      person.pose.x,
      person.pose.y,
      person.velocity.x,
      person.velocity.y};
    if (needs_transform) {
      geometry_msgs::msg::PointStamped source_point;
      source_point.header = snapshot->header;
      source_point.point.x = prepared.x;
      source_point.point.y = prepared.y;
      geometry_msgs::msg::PointStamped target_point;
      tf2::doTransform(source_point, target_point, transform);

      geometry_msgs::msg::Vector3Stamped source_velocity;
      source_velocity.header = snapshot->header;
      source_velocity.vector.x = prepared.vx;
      source_velocity.vector.y = prepared.vy;
      geometry_msgs::msg::Vector3Stamped target_velocity;
      tf2::doTransform(source_velocity, target_velocity, transform);

      prepared.x = target_point.point.x;
      prepared.y = target_point.point.y;
      prepared.vx = target_velocity.vector.x;
      prepared.vy = target_velocity.vector.y;
    }
    prepared_people_.push_back(std::move(prepared));
  }

  if (!logged_prepared_people_) {
    RCLCPP_INFO(
      logger_, "Prepared %zu non-ignored pedestrians in trajectory frame %s",
      prepared_people_.size(), target_frame.c_str());
    logged_prepared_people_ = true;
  }
  return true;
}

double ProxemicForceCritic::timeAtPose(
  const dwb_msgs::msg::Trajectory2D & trajectory, std::size_t index) const
{
  if (index == 0U || trajectory.time_offsets.empty()) {
    return 0.0;
  }
  const std::size_t offset_index =
    std::min(index, trajectory.time_offsets.size() - 1U);
  return rclcpp::Duration(trajectory.time_offsets[offset_index]).seconds();
}

double ProxemicForceCritic::scoreTrajectory(
  const dwb_msgs::msg::Trajectory2D & trajectory)
{
  if (prepared_people_.empty() || trajectory.poses.empty()) {
    return 0.0;
  }

  std::vector<TimedPoint> robot_poses;
  robot_poses.reserve(trajectory.poses.size());
  for (std::size_t index = 0; index < trajectory.poses.size(); ++index) {
    const auto & pose = trajectory.poses[index];
    robot_poses.push_back(TimedPoint{pose.x, pose.y, timeAtPose(trajectory, index)});
  }

  const double score = maximumProxemicScore(
    robot_poses, prepared_people_, ignored_identifiers_, comfort_distance_, sigma_);
  cycle_min_score_ = std::min(cycle_min_score_, score);
  cycle_max_score_ = std::max(cycle_max_score_, score);
  return score;
}

void ProxemicForceCritic::debrief(const nav_2d_msgs::msg::Twist2D &)
{
  if (!prepared_people_.empty() && std::isfinite(cycle_min_score_)) {
    RCLCPP_INFO_THROTTLE(
      logger_, *clock_, 5000,
      "ProxemicForceCritic raw candidate range: %.4f to %.4f (scale %.3f)",
      cycle_min_score_, cycle_max_score_, scale_);
  }
}

}  // namespace museum_social_critic

PLUGINLIB_EXPORT_CLASS(
  museum_social_critic::ProxemicForceCritic,
  dwb_core::TrajectoryCritic)
