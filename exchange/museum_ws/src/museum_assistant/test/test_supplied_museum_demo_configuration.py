import importlib.util
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[5]
PACKAGE = REPO_ROOT / "exchange/museum_ws/src/museum_assistant"
LAYOUT_PATH = PACKAGE / "config/supplied_museum_room_layout.yaml"
BASE_PATH = PACKAGE / "config/nav2_museum.yaml"
ODOM_OVERRIDE_PATH = PACKAGE / "config/nav2_ground_truth_odom_override.yaml"
DEMO_PATH = PACKAGE / "config/nav2_supplied_demo.yaml"
SOCIAL_PATH = PACKAGE / "config/nav2_supplied_social_force.yaml"
LAUNCH_PATH = PACKAGE / "launch/supplied_museum_demo_navigation.launch.py"
REASONING_LAUNCH_PATH = (
    PACKAGE / "launch/supplied_museum_reasoning_navigation.launch.py"
)
GENERATOR_PATH = REPO_ROOT / "scripts/generate_map_from_sdf_boxes.py"


def load_generator():
    spec = importlib.util.spec_from_file_location("demo_map_generator", GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def flattened(value, prefix=()):
    result = {}
    if isinstance(value, dict):
        for key, child in value.items():
            result.update(flattened(child, prefix + (key,)))
    else:
        result[prefix] = value
    return result


LAYOUT = yaml.safe_load(LAYOUT_PATH.read_text(encoding="utf-8"))
BASE = yaml.safe_load(BASE_PATH.read_text(encoding="utf-8"))
OVERRIDE = yaml.safe_load(ODOM_OVERRIDE_PATH.read_text(encoding="utf-8"))
DEMO = yaml.safe_load(DEMO_PATH.read_text(encoding="utf-8"))
SOCIAL = yaml.safe_load(SOCIAL_PATH.read_text(encoding="utf-8"))
GENERATOR = load_generator()
WIDTH, HEIGHT, CELLS = GENERATOR.rasterize(GENERATOR.load_boxes())


def test_exactly_four_physical_demo_candidates_exist():
    candidates = LAYOUT["candidate_poses"]
    assert {name for name, pose in candidates.items() if pose["demo_gallery"]} == {
        "candidate_central_gallery", "candidate_north",
        "candidate_south_west", "candidate_south_east",
    }


def test_central_gallery_candidate_is_valid_and_unobstructed():
    candidate = LAYOUT["candidate_poses"]["candidate_central_gallery"]
    assert (candidate["x"], candidate["y"], candidate["yaw"]) == (-3.5, 3.0, 0.0)
    assert candidate["area"] == "central_area"
    assert GENERATOR.map_value(candidate["x"], candidate["y"], WIDTH, HEIGHT, CELLS) == 254
    assert GENERATOR.clearance_from_map(candidate, WIDTH, HEIGHT, CELLS) == 3.15
    entrance = LAYOUT["physical_areas"]["entrance_area"]["validated_free_regions"][0]["bounds"]
    assert not (entrance["x_min"] <= candidate["x"] <= entrance["x_max"]
                and entrance["y_min"] <= candidate["y"] <= entrance["y_max"])
    for door in LAYOUT["doors"].values():
        bounds = door["map_free_region"]
        assert not (bounds["x_min"] <= candidate["x"] <= bounds["x_max"]
                    and bounds["y_min"] <= candidate["y"] <= bounds["y_max"])
    for marker in GENERATOR.marker_positions().values():
        assert ((candidate["x"] - marker["x"]) ** 2
                + (candidate["y"] - marker["y"]) ** 2) ** 0.5 > 0.46


def test_demo_configuration_has_only_the_bounded_differences():
    composed = yaml.safe_load(BASE_PATH.read_text(encoding="utf-8"))
    for node, body in OVERRIDE.items():
        composed[node]["ros__parameters"].update(body["ros__parameters"])
    before, after = flattened(composed), flattened(DEMO)
    changed = {path: (before.get(path), after.get(path))
               for path in before.keys() | after.keys()
               if before.get(path) != after.get(path)}
    assert changed == {
        ("amcl", "ros__parameters", "alpha1"): (0.2, 0.01),
        ("amcl", "ros__parameters", "alpha2"): (0.2, 0.01),
        ("amcl", "ros__parameters", "alpha3"): (0.2, 0.01),
        ("amcl", "ros__parameters", "alpha4"): (0.2, 0.01),
        ("amcl", "ros__parameters", "alpha5"): (0.2, 0.01),
        ("controller_server", "ros__parameters", "controller_frequency"): (15.0, 8.0),
        ("controller_server", "ros__parameters", "progress_checker", "required_movement_radius"): (0.10, 0.05),
        ("controller_server", "ros__parameters", "progress_checker", "movement_time_allowance"): (30.0, 90.0),
        ("controller_server", "ros__parameters", "general_goal_checker", "xy_goal_tolerance"): (0.4, 0.20),
        ("controller_server", "ros__parameters", "FollowPath", "max_vel_x"): (0.35, 0.20),
        ("controller_server", "ros__parameters", "FollowPath", "max_speed_xy"): (0.35, 0.20),
        ("controller_server", "ros__parameters", "FollowPath", "max_vel_theta"): (0.3, 0.25),
        ("controller_server", "ros__parameters", "FollowPath", "min_speed_xy"): (0.0, 0.05),
        ("controller_server", "ros__parameters", "FollowPath", "min_speed_theta"): (0.0, 0.20),
        ("controller_server", "ros__parameters", "FollowPath", "vx_samples"): (12, 3),
        ("controller_server", "ros__parameters", "FollowPath", "xy_goal_tolerance"): (0.4, 0.20),
        ("bt_navigator", "ros__parameters", "bt_loop_duration"): (10, 100),
        ("velocity_smoother", "ros__parameters", "max_velocity"): ([0.35, 0.0, 0.3], [0.20, 0.0, 0.25]),
        ("velocity_smoother", "ros__parameters", "min_velocity"): ([-0.15, 0.0, -0.3], [-0.15, 0.0, -0.25]),
    }


def test_demo_keeps_dwb_map_and_corrected_odometry_contract():
    controller = DEMO["controller_server"]["ros__parameters"]
    assert controller["FollowPath"]["plugin"] == "dwb_core::DWBLocalPlanner"
    assert controller["odom_topic"] == "/museum/ground_truth_odom"
    assert DEMO["bt_navigator"]["ros__parameters"]["odom_topic"] == "/museum/ground_truth_odom"
    assert DEMO["velocity_smoother"]["ros__parameters"]["odom_topic"] == "/museum/ground_truth_odom"
    assert DEMO["planner_server"]["ros__parameters"]["GridBased"]["allow_unknown"] is False
    assert DEMO["velocity_smoother"]["ros__parameters"]["max_velocity"] == [0.20, 0.0, 0.25]
    assert DEMO["velocity_smoother"]["ros__parameters"]["feedback"] == "OPEN_LOOP"
    assert controller["FollowPath"]["min_speed_theta"] == 0.20
    assert controller["FollowPath"]["min_speed_xy"] == 0.05
    assert (
        controller["FollowPath"]["max_vel_x"]
        / (controller["FollowPath"]["vx_samples"] - 1)
    ) == 0.10
    assert {
        DEMO["amcl"]["ros__parameters"][f"alpha{index}"]
        for index in range(1, 6)
    } == {0.01}


def test_final_launch_selects_supplied_map_demo_config_and_corrected_odom_world():
    source = LAUNCH_PATH.read_text(encoding="utf-8")
    assert "tiago_supplied_museum_ground_truth_odom.launch.py" in source
    assert "supplied_museum_nav.yaml" in source
    assert "nav2_supplied_demo.yaml" in source
    assert '"slam": "False"' in source
    assert "social" not in source


def test_supplied_social_force_config_only_adds_the_existing_critic():
    before, after = flattened(DEMO), flattened(SOCIAL)
    changed = {
        path: (before.get(path), after.get(path))
        for path in before.keys() | after.keys()
        if before.get(path) != after.get(path)
    }
    prefix = ("controller_server", "ros__parameters", "FollowPath")
    assert changed == {
        prefix + ("critics",): (
            [
                "RotateToGoal", "Oscillation", "BaseObstacle", "GoalAlign",
                "PathAlign", "PathDist", "GoalDist",
            ],
            [
                "RotateToGoal", "Oscillation", "BaseObstacle",
                "ProxemicForce", "GoalAlign", "PathAlign", "PathDist",
                "GoalDist",
            ],
        ),
        prefix + ("ProxemicForce.class",): (
            None, "museum_social_critic::ProxemicForceCritic",
        ),
        prefix + ("ProxemicForce.scale",): (None, 32.0),
        prefix + ("ProxemicForce.comfort_distance",): (None, 1.0),
        prefix + ("ProxemicForce.sigma",): (None, 0.4),
        prefix + ("ProxemicForce.people_topic",): (None, "/people"),
        prefix + ("ProxemicForce.people_timeout",): (None, 1.0),
        prefix + ("ProxemicForce.ignored_identifiers",): (
            None, ["visitor_1"],
        ),
    }


def test_supplied_social_force_preserves_critical_navigation_parameters():
    assert "ProxemicForce" not in DEMO["controller_server"][
        "ros__parameters"
    ]["FollowPath"]["critics"]
    assert SOCIAL["controller_server"]["ros__parameters"]["FollowPath"][
        "plugin"
    ] == "dwb_core::DWBLocalPlanner"
    assert SOCIAL["planner_server"]["ros__parameters"]["GridBased"][
        "allow_unknown"
    ] is False
    for node in ("amcl", "local_costmap", "global_costmap", "velocity_smoother"):
        assert SOCIAL[node] == DEMO[node]


def test_reasoning_launch_keeps_social_force_support_opt_in():
    navigation_source = LAUNCH_PATH.read_text(encoding="utf-8")
    reasoning_source = REASONING_LAUNCH_PATH.read_text(encoding="utf-8")
    assert 'LaunchConfiguration("nav2_params_file")' in navigation_source
    assert "nav2_supplied_demo.yaml" in navigation_source
    assert 'default_value="False"' in reasoning_source
    assert 'executable="simulated_people_node"' in reasoning_source
    assert 'LaunchConfiguration("publish_people")' in reasoning_source
