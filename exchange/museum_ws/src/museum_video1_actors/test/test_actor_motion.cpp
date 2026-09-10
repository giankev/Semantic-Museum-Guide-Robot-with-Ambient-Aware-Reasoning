#include <algorithm>
#include <cmath>
#include <iostream>
#include <limits>
#include <stdexcept>
#include "museum_video1_actors/motion.hpp"

void require(bool ok, const char * message)
{
  if (!ok) {throw std::runtime_error(message);}
}

int main()
{
  using museum_video1_actors::Ellipse;
  constexpr double pi = 3.14159265358979323846;
  const Ellipse e{1.8, 8.7, 0.45, 1.3, 0.28, 0.0};
  e.validate();
  double minimum = 100, maximum = 0, sum = 0;
  constexpr int count = 10001;
  for (int i = 0; i < count; ++i) {
    const double t = i * (2*pi/e.omega)/(count-1);
    const auto s = e.at(t);
    const auto before = e.at(t-1e-5);
    const auto after = e.at(t+1e-5);
    require(std::abs((after.x-before.x)/2e-5-s.vx) < 1e-7, "Incorrect vx");
    require(std::abs((after.y-before.y)/2e-5-s.vy) < 1e-7, "Incorrect vy");
    require(s.x >= 1.35-1e-12 && s.x <= 2.25+1e-12, "Leaves lateral lane");
    require(s.y >= 7.4-1e-12 && s.y <= 10.0+1e-12, "Leaves gallery opening");
    const double speed = std::hypot(s.vx, s.vy);
    require(speed > 0.10 && speed < 0.5, "Invalid walking speed");
    require(std::abs(std::sin(s.yaw)*speed-s.vy) < 1e-12, "Wrong public heading");
    minimum = std::min(minimum, speed); maximum = std::max(maximum, speed); sum += speed;
  }
  const auto first=e.at(0), last=e.at(2*pi/e.omega);
  require(std::hypot(first.x-last.x, first.y-last.y) < 1e-12, "Position jumps on wrap");
  require(std::hypot(first.vx-last.vx, first.vy-last.vy) < 1e-12, "Velocity jumps on wrap");
  for (double invalid : {0.0, -1.0, std::numeric_limits<double>::infinity()}) {
    bool rejected = false;
    try {Ellipse{0, 0, invalid, 1, 1, 0}.validate();} catch (const std::invalid_argument &) {rejected = true;}
    require(rejected, "Invalid path was accepted");
  }
  std::cout << "PASS: 10001 samples; analytic speed min/mean/max " << minimum << "/"
            << sum/count << "/" << maximum << " m/s; >0.10 m/s: 100%. NOT a Gazebo runtime test.\n";
}
