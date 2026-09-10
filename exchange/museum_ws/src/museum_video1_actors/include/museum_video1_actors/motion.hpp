#pragma once
#include <cmath>
#include <initializer_list>
#include <stdexcept>

namespace museum_video1_actors
{
struct Sample {double x, y, yaw, vx, vy;};
struct Ellipse
{
  double cx, cy, rx, ry, omega, phase;
  void validate() const
  {
    for (double value : {cx, cy, rx, ry, omega, phase}) {
      if (!std::isfinite(value)) {throw std::invalid_argument("Nonfinite actor path");}
    }
    if (rx <= 0.0 || ry <= 0.0 || omega == 0.0) {
      throw std::invalid_argument("Degenerate actor path");
    }
  }
  Sample at(double t) const
  {
    const double angle = phase + omega * t;
    const double vx = -rx * omega * std::sin(angle);
    const double vy = ry * omega * std::cos(angle);
    return {cx + rx * std::cos(angle), cy + ry * std::sin(angle),
      std::atan2(vy, vx), vx, vy};
  }
};
}  // namespace museum_video1_actors
