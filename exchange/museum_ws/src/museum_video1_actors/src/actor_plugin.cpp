// SPDX-License-Identifier: Apache-2.0
#include <cmath>
#include <functional>
#include <memory>
#include <stdexcept>
#include <gazebo/common/common.hh>
#include <gazebo/common/Mesh.hh>
#include <gazebo/common/Skeleton.hh>
#include <gazebo/common/SkeletonAnimation.hh>
#include <gazebo/physics/physics.hh>
#include <gazebo_ros/node.hpp>
#include <social_nav_msgs/msg/pedestrians.hpp>
#include "museum_video1_actors/motion.hpp"

namespace museum_video1_actors
{
// A MODEL plugin attached only to an <actor>. Never moves a robot model.
// One actor is deliberately the only supported stage until runtime acceptance.
class ActorPlugin : public gazebo::ModelPlugin
{
public:
  void Load(gazebo::physics::ModelPtr model, sdf::ElementPtr sdf) override
  {
    actor_ = boost::dynamic_pointer_cast<gazebo::physics::Actor>(model);
    if (!actor_ || actor_->GetName() != "video1_walker_1") {
      gzerr << "Video 1 plugin requires the allowlisted actor video1_walker_1\n";
      return;
    }
    try {
      path_ = {sdf->Get<double>("cx"), sdf->Get<double>("cy"),
        sdf->Get<double>("rx"), sdf->Get<double>("ry"),
        sdf->Get<double>("omega"), sdf->Get<double>("phase")};
      path_.validate();
      auto animations = actor_->SkeletonAnimations();
      if (!animations.count("walking") || !animations.at("walking")) {
        throw std::runtime_error("walk.dae skeleton animation did not load");
      }
      // Same skin and animation: their root joint names match. Derive average
      // gait seconds/metre from the asset instead of inventing a walking rate.
      auto animation = animations.at("walking");
      const auto root = actor_->Mesh()->GetSkeleton()->GetRootNode()->GetName();
      const double duration = animation->GetLength();
      const auto first = animation->NodePoseAt(root, 0.0, false).Translation();
      const auto last = animation->NodePoseAt(root, duration, false).Translation();
      const double stride = std::abs(last.X() - first.X());
      if (!std::isfinite(duration) || duration <= 0.0 || !std::isfinite(stride) || stride < 0.01) {
        throw std::runtime_error("walk.dae has no usable root translation");
      }
      animation_factor_ = duration / stride;
      node_ = gazebo_ros::Node::Get(sdf);
      publisher_ = node_->create_publisher<social_nav_msgs::msg::Pedestrians>(
        "/museum/video1/actor_states", rclcpp::QoS(10));
      Reset();
      update_ = gazebo::event::Events::ConnectWorldUpdateBegin(
        std::bind(&ActorPlugin::OnUpdate, this, std::placeholders::_1));
      RCLCPP_INFO(node_->get_logger(),
        "Walking skeleton loaded; gait factor %.6f s/m; actor states 20 Hz in world", animation_factor_);
    } catch (const std::exception & e) {
      gzerr << "Video 1 actor initialization failed: " << e.what() << "\n";
    }
  }

  void Reset() override
  {
    if (!publisher_) {return;}
    gazebo::physics::TrajectoryInfoPtr info(new gazebo::physics::TrajectoryInfo());
    info->type = "walking";
    info->duration = 1.0;
    info->translated = true;
    actor_->SetCustomTrajectory(info);
    actor_->Play();
    epoch_ = actor_->GetWorld()->SimTime().Double();
    last_update_ = epoch_;
    last_publish_ = epoch_;
    actor_->SetScriptTime(0.0);
    Apply(path_.at(0.0));
  }

private:
  void Apply(const Sample & s)
  {
    // Gazebo's shipped walk.dae uses the same roll/yaw convention as
    // gazebo11/plugins/ActorPlugin.cc. Public heading excludes this mesh offset.
    constexpr double half_pi = 1.5707963267948966;
    actor_->SetWorldPose(
      ignition::math::Pose3d(s.x, s.y, 1.2138, half_pi, 0.0, s.yaw + half_pi),
      false, false);
  }

  void OnUpdate(const gazebo::common::UpdateInfo & info)
  {
    const double now = info.simTime.Double();
    if (now < last_update_) {Reset(); return;}
    if (now <= last_update_) {return;}
    const Sample s = path_.at(now - epoch_);
    const auto old = actor_->WorldPose().Pos();
    Apply(s);
    // Read back the actual actor pose; missing/failed actors cannot create a
    // parallel Python prediction stream that keeps claiming successful motion.
    const auto actual = actor_->WorldPose().Pos();
    actor_->SetScriptTime(actor_->ScriptTime() + (actual - old).Length() * animation_factor_);
    last_update_ = now;
    if (now - last_publish_ < 0.05 - 1e-9) {return;}
    last_publish_ = now;
    social_nav_msgs::msg::Pedestrians output;
    output.header.stamp.sec = info.simTime.sec;
    output.header.stamp.nanosec = info.simTime.nsec;
    output.header.frame_id = "world";
    social_nav_msgs::msg::Pedestrian person;
    person.identifier = "walker_1";
    person.pose.x = actual.X();
    person.pose.y = actual.Y();
    person.pose.theta = s.yaw;
    // Analytic derivative of the pose applied in this same physics callback.
    // This is neither Gazebo static-model twist nor 1 Hz position differencing.
    person.velocity.x = s.vx;
    person.velocity.y = s.vy;
    output.pedestrians.push_back(person);
    publisher_->publish(output);
  }

  gazebo::physics::ActorPtr actor_;
  gazebo_ros::Node::SharedPtr node_;
  gazebo::event::ConnectionPtr update_;
  rclcpp::Publisher<social_nav_msgs::msg::Pedestrians>::SharedPtr publisher_;
  Ellipse path_{};
  double epoch_{0.0}, last_update_{0.0}, last_publish_{0.0}, animation_factor_{0.0};
};
GZ_REGISTER_MODEL_PLUGIN(ActorPlugin)
}  // namespace museum_video1_actors
