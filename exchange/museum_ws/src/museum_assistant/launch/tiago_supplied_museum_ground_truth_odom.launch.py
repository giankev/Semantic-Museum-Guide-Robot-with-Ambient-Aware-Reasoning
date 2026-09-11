"""Opt-in supplied-museum simulation with sole ground-truth odom TF authority."""

from pathlib import Path
import shlex

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument, ExecuteProcess, IncludeLaunchDescription
from launch.launch_description_sources import PythonLaunchDescriptionSource
from launch.substitutions import LaunchConfiguration


def _controller_reloader_command() -> str:
    pmb2_share = Path(get_package_share_directory("pmb2_controller_configuration"))
    museum_share = Path(get_package_share_directory("museum_assistant"))
    public_config = pmb2_share / "config" / "mobile_base_controller_public_sim.yaml"
    override = museum_share / "config" / "mobile_base_ground_truth_odom_override.yaml"
    configs = f"-p {shlex.quote(str(public_config))} -p {shlex.quote(str(override))}"
    return (
        "ready=false; "
        "for attempt in $(seq 1 60); do "
        "ros2 control list_controllers 2>/dev/null | "
        "sed -r 's/\\x1B\\[[0-9;]*[mK]//g' | "
        "grep -Eq '^mobile_base_controller[[:space:]]+[^[:space:]]+[[:space:]]+active[[:space:]]*$' && ready=true && break; "
        "sleep 1; done; "
        "test \"$ready\" = true && "
        "ros2 control switch_controllers --deactivate mobile_base_controller --strict && "
        "ros2 control unload_controller mobile_base_controller && "
        "ros2 run controller_manager spawner mobile_base_controller "
        f"{configs} --controller-manager-timeout 20 --switch-timeout 20 && "
        "test \"$(ros2 param get /mobile_base_controller enable_odom_tf | tail -n 1)\" "
        "= 'Boolean value is: False' && "
        "exec ros2 run museum_assistant simulation_ground_truth_odom "
        "--ros-args -p enabled:=true -p use_sim_time:=true"
    )


def generate_launch_description():
    package_share = Path(get_package_share_directory("museum_assistant"))
    world_launch = package_share / "launch" / "tiago_supplied_museum_nav_world.launch.py"
    return LaunchDescription(
        [
            DeclareLaunchArgument(
                "world_file",
                default_value=str(package_share / "worlds" / "supplied_museum" / "museum_nav.world"),
                description="Optional isolated demo world; default is unchanged.",
            ),
            DeclareLaunchArgument(
                "gzclient",
                default_value="False",
                choices=["True", "False"],
                description="Start the Gazebo Classic graphical client.",
            ),
            IncludeLaunchDescription(
                PythonLaunchDescriptionSource(str(world_launch)),
                launch_arguments={
                    "gzclient": LaunchConfiguration("gzclient"),
                    "world_file": LaunchConfiguration("world_file"),
                }.items(),
            ),
            ExecuteProcess(
                cmd=["bash", "-lc", _controller_reloader_command()],
                output="screen",
                name="ground_truth_odom_controller_gate",
            ),
        ]
    )
