#include <gtest/gtest.h>

#include <unordered_set>
#include <vector>

#include "museum_social_critic/proxemic_force_critic.hpp"

namespace msc = museum_social_critic;

TEST(ProxemicMath, FartherPersonHasLowerScore)
{
  EXPECT_LT(msc::proxemicCost(2.0, 1.0, 0.4), msc::proxemicCost(1.0, 1.0, 0.4));
}

TEST(ProxemicMath, VeryClosePersonHasHighScore)
{
  EXPECT_GT(msc::proxemicCost(0.1, 1.0, 0.4), 0.8);
}

TEST(ProxemicMath, ZeroPeopleProducesZeroScore)
{
  const std::vector<msc::TimedPoint> poses{{0.0, 0.0, 0.0}};
  EXPECT_DOUBLE_EQ(
    msc::maximumProxemicScore(poses, {}, {}, 1.0, 0.4), 0.0);
}

TEST(ProxemicMath, IgnoredVisitorContributesNoScore)
{
  const std::vector<msc::TimedPoint> poses{{0.0, 0.0, 0.0}};
  const std::vector<msc::PersonState> people{{"visitor_1", 0.0, 0.0, 0.0, 0.0}};
  const std::unordered_set<std::string> ignored{"visitor_1"};
  EXPECT_DOUBLE_EQ(
    msc::maximumProxemicScore(poses, people, ignored, 1.0, 0.4), 0.0);
}

TEST(ProxemicMath, ConstantVelocityChangesEncounterScore)
{
  const std::vector<msc::TimedPoint> poses{{0.0, 0.0, 1.0}};
  const std::vector<msc::PersonState> static_person{{"guide_1", 2.0, 0.0, 0.0, 0.0}};
  const std::vector<msc::PersonState> approaching{{"guide_1", 2.0, 0.0, -1.0, 0.0}};
  EXPECT_GT(
    msc::maximumProxemicScore(poses, approaching, {}, 1.0, 0.4),
    msc::maximumProxemicScore(poses, static_person, {}, 1.0, 0.4));
}

TEST(ProxemicMath, MaximumDoesNotGrowWithRepeatedSamples)
{
  const std::vector<msc::TimedPoint> one_pose{{0.0, 0.0, 0.0}};
  const std::vector<msc::TimedPoint> repeated(10, msc::TimedPoint{0.0, 0.0, 0.0});
  const std::vector<msc::PersonState> people{{"guide_1", 1.0, 0.0, 0.0, 0.0}};
  EXPECT_DOUBLE_EQ(
    msc::maximumProxemicScore(one_pose, people, {}, 1.0, 0.4),
    msc::maximumProxemicScore(repeated, people, {}, 1.0, 0.4));
}
