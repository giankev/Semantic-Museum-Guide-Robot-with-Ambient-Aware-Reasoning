import importlib.util
import math
from pathlib import Path
import sys

import pytest
import yaml


PACKAGE_ROOT = Path(__file__).resolve().parents[1]
HELPERS = PACKAGE_ROOT / "museum_assistant" / "simulation_ground_truth_odom.py"
NODE = PACKAGE_ROOT / "museum_assistant" / "simulation_ground_truth_odom_node.py"
LAUNCH = PACKAGE_ROOT / "launch" / "tiago_supplied_museum_ground_truth_odom.launch.py"
CONTROLLER_OVERRIDE = PACKAGE_ROOT / "config" / "mobile_base_ground_truth_odom_override.yaml"
NAV2_OVERRIDE = PACKAGE_ROOT / "config" / "nav2_ground_truth_odom_override.yaml"


def load_helpers():
    spec = importlib.util.spec_from_file_location("simulation_ground_truth_odom", HELPERS)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


helpers = load_helpers()


def quaternion(yaw):
    return helpers.quaternion_from_yaw(yaw)


def test_initial_world_pose_maps_exactly_to_odom_origin():
    alignment = helpers.PlanarAlignment.from_pose((4.0, -2.0, 0.3), quaternion(0.7))
    position, orientation = alignment.apply((4.0, -2.0, 0.3), quaternion(0.7))
    assert position == pytest.approx((0.0, 0.0, 0.0))
    assert helpers.yaw_from_quaternion(orientation) == pytest.approx(0.0)


def test_alignment_rotates_world_displacement_into_initial_heading():
    alignment = helpers.PlanarAlignment.from_pose((2.0, 3.0, 0.0), quaternion(math.pi / 2))
    position, orientation = alignment.apply((2.0, 5.0, 0.0), quaternion(math.pi))
    assert position == pytest.approx((2.0, 0.0, 0.0), abs=1e-12)
    assert helpers.yaw_from_quaternion(orientation) == pytest.approx(math.pi / 2)


def test_quaternion_yaw_conversion_normalizes_input():
    scaled = tuple(value * 3.0 for value in quaternion(-1.2))
    assert helpers.yaw_from_quaternion(scaled) == pytest.approx(-1.2)


@pytest.mark.parametrize(
    "position,orientation,linear,angular",
    [
        ((math.nan, 0.0, 0.0), quaternion(0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ((0.0, 0.0, 0.0), (0.0, 0.0, 0.0, 0.0), (0.0, 0.0, 0.0), (0.0, 0.0, 0.0)),
        ((0.0, 0.0, 0.0), quaternion(0.0), (math.inf, 0.0, 0.0), (0.0, 0.0, 0.0)),
    ],
)
def test_nonfinite_or_invalid_samples_are_rejected(position, orientation, linear, angular):
    with pytest.raises(ValueError):
        helpers.validate_sample(position, orientation, linear, angular)


def test_timestamps_are_finite_ros_time_and_strictly_increasing():
    assert helpers.validate_timestamp(3, 4) == 3_000_000_004
    with pytest.raises(ValueError):
        helpers.validate_timestamp(3, 4, 3_000_000_004)
    with pytest.raises(ValueError):
        helpers.validate_timestamp(0, 1_000_000_000)


def test_stale_detection_has_a_strict_deterministic_boundary():
    assert not helpers.is_stale(1_500, 1_000, 500)
    assert helpers.is_stale(1_501, 1_000, 500)
    assert not helpers.is_stale(10_000, None, 500)


def test_alignment_output_is_deterministic():
    alignment = helpers.PlanarAlignment.from_pose((1.0, 2.0, 0.0), quaternion(0.3))
    sample = ((4.0, 5.0, 0.0), quaternion(-0.2))
    assert alignment.apply(*sample) == alignment.apply(*sample)


def test_covariances_are_finite_nonnegative_and_have_six_documented_diagonals():
    for covariance, diagonal in (
        (helpers.POSE_COVARIANCE, helpers.POSE_COVARIANCE_DIAGONAL),
        (helpers.TWIST_COVARIANCE, helpers.TWIST_COVARIANCE_DIAGONAL),
    ):
        assert len(covariance) == 36
        assert all(math.isfinite(value) and value >= 0 for value in covariance)
        assert tuple(covariance[index] for index in (0, 7, 14, 21, 28, 35)) == diagonal


def test_node_contract_preserves_twist_and_uses_required_frames():
    text = NODE.read_text(encoding="utf-8")
    assert "output.twist.twist = deepcopy(source.twist.twist)" in text
    assert "output.header.frame_id = ODOM_FRAME" in text
    assert "output.child_frame_id = BASE_FRAME" in text
    assert '"/museum/ground_truth_odom"' in text
    assert '"/ground_truth_odom"' in text
    assert "cmd_vel" not in text
    assert "map->odom" not in text and "map_to_odom" not in text


def test_adapter_requires_explicit_opt_in_and_sim_time():
    node_text = NODE.read_text(encoding="utf-8")
    launch_text = LAUNCH.read_text(encoding="utf-8")
    assert 'declare_parameter("enabled", False)' in node_text
    assert 'get_parameter("use_sim_time")' in node_text
    assert "-p enabled:=true -p use_sim_time:=true" in launch_text


def test_launch_gate_prevents_duplicate_odom_tf_authority():
    override = yaml.safe_load(CONTROLLER_OVERRIDE.read_text(encoding="utf-8"))
    assert override["mobile_base_controller"]["ros__parameters"]["enable_odom_tf"] is False
    launch_text = LAUNCH.read_text(encoding="utf-8")
    assert "unload_controller mobile_base_controller" in launch_text
    assert launch_text.index("spawner mobile_base_controller") < launch_text.index(
        "exec ros2 run museum_assistant simulation_ground_truth_odom"
    )
    assert "Boolean value is: False" in launch_text


def test_nav2_override_changes_only_odometry_consumers():
    config = yaml.safe_load(NAV2_OVERRIDE.read_text(encoding="utf-8"))
    assert config == {
        "controller_server": {"ros__parameters": {"odom_topic": "/museum/ground_truth_odom"}},
        "bt_navigator": {"ros__parameters": {"odom_topic": "/museum/ground_truth_odom"}},
        "velocity_smoother": {"ros__parameters": {"odom_topic": "/museum/ground_truth_odom"}},
    }
