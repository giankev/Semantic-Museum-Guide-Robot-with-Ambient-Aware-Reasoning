#include <gtest/gtest.h>

#include <cmath>
#include <limits>
#include <unordered_set>
#include <vector>

#include "museum_social_critic/proxemic_force_critic.hpp"

namespace msc = museum_social_critic;

TEST(ProxemicMath, StationaryPersonWithZeroHeadingThresholdIsIsotropic)
{
  EXPECT_DOUBLE_EQ(msc::effectiveProxemicDistance(3, 4, 0, 0, true, 1.4, 1, .8, 0), 5);
}

TEST(ProxemicMath, SnapshotAgeIsIncludedBeforeTrajectoryPrediction)
{
  msc::PersonState person{"walker_1", 2, 0, -1, 0};
  ASSERT_TRUE(msc::advancePersonToNow(person, .4, 1));
  EXPECT_NEAR(msc::maximumProxemicScore({{0, 0, .6}}, {person}, {}, 1, .4), .5, 1e-12);
}

TEST(ProxemicMath, FutureStaleAndNonfiniteStatesAreRejected)
{
  msc::PersonState person{"walker_1", 2, 0, -1, 0};
  EXPECT_FALSE(msc::advancePersonToNow(person, -.01, 1));
  EXPECT_FALSE(msc::advancePersonToNow(person, 1.01, 1));
  person.vx = std::numeric_limits<double>::quiet_NaN();
  EXPECT_FALSE(msc::advancePersonToNow(person, .1, 1));
}

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

TEST(ProxemicMath, DisabledAnisotropyIsExactIsotropicRegression)
{
  const std::vector<msc::TimedPoint> poses{{1.0, 2.0, 0.5}};
  const std::vector<msc::PersonState> people{{"guide_1", 0.2, 0.4, 0.3, -0.1}};
  const double predicted_x = 0.2 + 0.3 * 0.5;
  const double predicted_y = 0.4 - 0.1 * 0.5;
  const double expected = msc::proxemicCost(
    std::hypot(1.0 - predicted_x, 2.0 - predicted_y), 1.0, 0.4);
  EXPECT_DOUBLE_EQ(
    msc::maximumProxemicScore(
      poses, people, {}, 1.0, 0.4, false, 1.4, 1.0, 0.8, 0.1),
    expected);
}

TEST(ProxemicMath, MovingPersonScoresFrontAboveSideAboveBack)
{
  const std::vector<msc::PersonState> person{{"guide_1", 0.0, 0.0, 1.0, 0.0}};
  const auto score = [&person](double x, double y) {
      return msc::maximumProxemicScore(
        {{x, y, 0.0}}, person, {}, 1.0, 0.4, true, 1.4, 1.0, 0.8, 0.1);
    };
  const double front = score(1.0, 0.0);
  const double side = score(0.0, 1.0);
  const double back = score(-1.0, 0.0);
  EXPECT_GT(front, side);
  EXPECT_GT(side, back);
}

TEST(ProxemicMath, SlowPersonFallsBackExactlyToIsotropicDistance)
{
  const std::vector<msc::TimedPoint> poses{{0.5, 0.8, 0.0}};
  const std::vector<msc::PersonState> person{{"guide_1", 0.0, 0.0, 0.05, 0.0}};
  EXPECT_DOUBLE_EQ(
    msc::maximumProxemicScore(
      poses, person, {}, 1.0, 0.4, true, 1.4, 1.0, 0.8, 0.1),
    msc::maximumProxemicScore(poses, person, {}, 1.0, 0.4));
}

TEST(ProxemicMath, AnisotropicScoreIsRotationInvariant)
{
  const std::vector<msc::TimedPoint> original{{1.0, 0.5, 0.0}};
  const std::vector<msc::PersonState> heading_x{{"guide_1", 0.0, 0.0, 1.0, 0.0}};
  const std::vector<msc::TimedPoint> rotated{{-0.5, 1.0, 0.0}};
  const std::vector<msc::PersonState> heading_y{{"guide_1", 0.0, 0.0, 0.0, 1.0}};
  EXPECT_NEAR(
    msc::maximumProxemicScore(
      original, heading_x, {}, 1.0, 0.4, true, 1.4, 1.0, 0.8, 0.1),
    msc::maximumProxemicScore(
      rotated, heading_y, {}, 1.0, 0.4, true, 1.4, 1.0, 0.8, 0.1),
    1.0e-12);
}
