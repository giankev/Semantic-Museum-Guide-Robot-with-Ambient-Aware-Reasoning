"""Single-actor POC, baseline or unchanged static placement, in an isolated runtime."""
from pathlib import Path
from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, IncludeLaunchDescription, OpaqueFunction, TimerAction, ExecuteProcess, GroupAction
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node, SetRemap


def setup(context):
    museum = Path(get_package_share_directory('museum_assistant'))
    mode = LaunchConfiguration('mode').perform(context)
    gui = LaunchConfiguration('gzclient').perform(context)
    count = int(LaunchConfiguration('actor_count').perform(context))
    yielding = LaunchConfiguration('social_yield').perform(context) == 'true'
    nav = Path(get_package_share_directory('nav2_bringup')) / 'launch/bringup_launch.py'
    actions = [IncludeLaunchDescription(
        PythonLaunchDescriptionSource(str(museum / 'launch/tiago_supplied_museum_ground_truth_odom.launch.py')),
        launch_arguments={'gzclient': gui, 'world_file': LaunchConfiguration('world_file')}.items()),
        TimerAction(period=15.0, actions=[GroupAction(actions=([
            SetRemap(src='cmd_vel', dst='/cmd_vel_nav'),
            SetRemap(src='cmd_vel_smoothed', dst='/museum/nav_cmd_vel')] if yielding else []) + [IncludeLaunchDescription(
            PythonLaunchDescriptionSource(str(nav)), launch_arguments={
                'map': str(museum / 'maps/supplied_museum_nav.yaml'),
                'params_file': LaunchConfiguration('params_file'),
                'use_sim_time': 'true', 'autostart': 'true',
                'use_composition': 'False', 'slam': 'False'}.items())])])]
    if mode == 'actor':
        actions.append(Node(package='museum_video1_actors', executable='people_bridge.py',
                            parameters=[{'use_sim_time': True, 'actor_count': count}], output='screen'))
    elif mode == 'static':
        actions.extend([
            Node(package='museum_assistant', executable='simulated_people_node',
                 parameters=[{'use_sim_time': True}], output='screen'),
            ExecuteProcess(cmd=['python3', LaunchConfiguration('static_script'),
                                '--ros-args', '-p', 'use_sim_time:=true'], output='screen')])
    if yielding:
        actions.append(Node(package='museum_video1_actors', executable='social_yield.py',
            parameters=[str(Path(get_package_share_directory('museum_video1_actors')) / 'config/social_yield.yaml')],
            output='screen'))
    if gui == 'True':
        actions.extend([
            Node(package='museum_video1_actors', executable='social_markers.py',
                 parameters=[{'use_sim_time': True}], output='screen'),
            Node(package='rviz2', executable='rviz2',
                 arguments=['-d', LaunchConfiguration('rviz_config')],
                 parameters=[{'use_sim_time': True}], output='screen')])
    return actions


def generate_launch_description():
    return LaunchDescription([
        DeclareLaunchArgument('world_file'),
        DeclareLaunchArgument('actor_count', default_value='1'),
        DeclareLaunchArgument('social_yield', default_value='false', choices=['true', 'false']),
        DeclareLaunchArgument('rviz_config'),
        DeclareLaunchArgument('static_script'),
        DeclareLaunchArgument('params_file', default_value=str(
            Path(get_package_share_directory('museum_assistant')) / 'config/nav2_supplied_anisotropic.yaml')),
        DeclareLaunchArgument('mode', default_value='actor', choices=['baseline', 'static', 'actor']),
        DeclareLaunchArgument('gzclient', default_value='True', choices=['True', 'False']),
        OpaqueFunction(function=setup)])
