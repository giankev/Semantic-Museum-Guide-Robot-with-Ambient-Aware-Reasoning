#ifndef MUSEUM_SOCIAL_CRITIC__PROXEMIC_FORCE_CRITIC_HPP_
#define MUSEUM_SOCIAL_CRITIC__PROXEMIC_FORCE_CRITIC_HPP_

#include <limits>
#include <memory>
#include <mutex>
#include <string>
#include <unordered_set>
#include <vector>

#include "dwb_core/trajectory_critic.hpp"
#include "rclcpp/rclcpp.hpp"
#include "social_nav_msgs/msg/pedestrians.hpp"

namespace museum_social_critic
{

struct TimedPoint
{
  double x;
  double y;
  double time;
};

struct PersonState
{
  std::string identifier;
  double x;
  double y;
  double vx;
  double vy;
};

double proxemicCost(double distance, double comfort_distance, double sigma);

double maximumProxemicScore(
  const std::vector<TimedPoint> & robot_poses,
  const std::vector<PersonState> & people,
  const std::unordered_set<std::string> & ignored_identifiers,
  double comfort_distance,
  double sigma);

class ProxemicForceCritic : public dwb_core::TrajectoryCritic
{
public:
  void onInit() override;

  bool prepare(
    const geometry_msgs::msg::Pose2D & pose,
    const nav_2d_msgs::msg::Twist2D & velocity,
    const geometry_msgs::msg::Pose2D & goal,
    const nav_2d_msgs::msg::Path2D & global_plan) override;

  double scoreTrajectory(const dwb_msgs::msg::Trajectory2D & trajectory) override;

  void debrief(const nav_2d_msgs::msg::Twist2D & command) override;

private:
  void peopleCallback(const social_nav_msgs::msg::Pedestrians::SharedPtr message);
  double timeAtPose(const dwb_msgs::msg::Trajectory2D & trajectory, std::size_t index) const;

  rclcpp::Subscription<social_nav_msgs::msg::Pedestrians>::SharedPtr people_subscription_;
  rclcpp::Clock::SharedPtr clock_;
  rclcpp::Logger logger_{rclcpp::get_logger("ProxemicForceCritic")};

  std::mutex people_mutex_;
  social_nav_msgs::msg::Pedestrians::SharedPtr latest_people_;
  std::vector<PersonState> prepared_people_;
  std::unordered_set<std::string> ignored_identifiers_;

  std::string people_topic_;
  double comfort_distance_{1.0};
  double sigma_{0.4};
  double people_timeout_{1.0};
  double cycle_min_score_{std::numeric_limits<double>::infinity()};
  double cycle_max_score_{0.0};
  bool logged_snapshot_{false};
  bool logged_prepared_people_{false};
};

}  // namespace museum_social_critic

#endif  // MUSEUM_SOCIAL_CRITIC__PROXEMIC_FORCE_CRITIC_HPP_
