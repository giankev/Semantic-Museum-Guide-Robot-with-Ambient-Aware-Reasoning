cmake_minimum_required(VERSION 3.8)
project(museum_social_critic)

if(NOT CMAKE_CXX_STANDARD)
  set(CMAKE_CXX_STANDARD 17)
endif()

find_package(ament_cmake REQUIRED)
find_package(dwb_core REQUIRED)
find_package(dwb_msgs REQUIRED)
find_package(geometry_msgs REQUIRED)
find_package(nav_2d_msgs REQUIRED)
find_package(nav2_costmap_2d REQUIRED)
find_package(nav2_util REQUIRED)
find_package(pluginlib REQUIRED)
find_package(rclcpp REQUIRED)
find_package(social_nav_msgs REQUIRED)
find_package(tf2 REQUIRED)
find_package(tf2_geometry_msgs REQUIRED)

add_library(${PROJECT_NAME} SHARED
  src/proxemic_force_critic.cpp
)
target_include_directories(${PROJECT_NAME} PUBLIC
  $<BUILD_INTERFACE:${CMAKE_CURRENT_SOURCE_DIR}/include>
  $<INSTALL_INTERFACE:include>
)
ament_target_dependencies(${PROJECT_NAME}
  dwb_core
  dwb_msgs
  geometry_msgs
  nav_2d_msgs
  nav2_costmap_2d
  nav2_util
  pluginlib
  rclcpp
  social_nav_msgs
  tf2
  tf2_geometry_msgs
)

pluginlib_export_plugin_description_file(dwb_core critics.xml)

install(TARGETS ${PROJECT_NAME}
  ARCHIVE DESTINATION lib
  LIBRARY DESTINATION lib
  RUNTIME DESTINATION bin
)
install(DIRECTORY include/ DESTINATION include)
install(FILES critics.xml DESTINATION share/${PROJECT_NAME})

if(BUILD_TESTING)
  find_package(ament_cmake_gtest REQUIRED)
  ament_add_gtest(test_proxemic_math test/test_proxemic_math.cpp)
  target_link_libraries(test_proxemic_math ${PROJECT_NAME})
endif()

ament_export_include_directories(include)
ament_export_libraries(${PROJECT_NAME})
ament_export_dependencies(
  dwb_core
  dwb_msgs
  geometry_msgs
  nav_2d_msgs
  nav2_costmap_2d
  nav2_util
  pluginlib
  rclcpp
  social_nav_msgs
  tf2
  tf2_geometry_msgs
)

ament_package()
