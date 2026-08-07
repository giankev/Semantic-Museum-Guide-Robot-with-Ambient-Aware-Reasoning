from pathlib import Path
import xml.etree.ElementTree as ET

import pytest
import yaml

from museum_assistant.supplied_museum_navigation import (
    GoalSequence,
    LocalizationMonitor,
    TimedPose,
    TrinaryOccupancyMap,
    load_route_plan,
    route_action_kind,
)
from museum_assistant.supplied_museum_route_runner import (
    parse_args,
    terminal_localization_is_fresh,
)


REPO_ROOT = Path(__file__).resolve().parents[5]
PACKAGE = REPO_ROOT / "exchange/museum_ws/src/museum_assistant"
ROUTES_PATH = PACKAGE / "config/supplied_museum_routes.yaml"
LAYOUT_PATH = PACKAGE / "config/supplied_museum_room_layout.yaml"
MAP_PATH = PACKAGE / "maps/supplied_museum_nav.yaml"
ROUTE_BT_PATH = PACKAGE / "behavior_trees/supplied_museum_to_pose.xml"
ACCEPTANCE_SCRIPT = (
    REPO_ROOT / "scripts/supplied_museum_navigation_acceptance.sh"
)


def test_navigator_loads_all_four_complete_routes():
    expected = {
        "central_gallery": ["candidate_central_gallery"],
        "north_gallery": ["candidate_north"],
        "south_west_gallery": [
            "south_entry",
            "south_junction",
            "south_inner_gap",
            "south_west_door_approach",
            "candidate_south_west",
        ],
        "south_east_gallery": [
            "south_entry",
            "south_junction",
            "south_inner_gap",
            "south_east_door_approach",
            "candidate_south_east",
        ],
    }
    for destination, names in expected.items():
        route = load_route_plan(destination, ROUTES_PATH, LAYOUT_PATH)
        assert [pose.name for pose in route] == names


def test_navigator_rejects_unknown_and_duplicate_waypoints(tmp_path):
    with pytest.raises(
        ValueError, match="unknown supplied-museum destination"
    ):
        load_route_plan("missing_gallery", ROUTES_PATH, LAYOUT_PATH)

    routes = yaml.safe_load(ROUTES_PATH.read_text(encoding="utf-8"))
    routes["routes"]["south_west_gallery"].insert(1, "south_entry")
    invalid_path = tmp_path / "routes.yaml"
    invalid_path.write_text(yaml.safe_dump(routes), encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate waypoint names"):
        load_route_plan("south_west_gallery", invalid_path, LAYOUT_PATH)


def test_goal_sequence_never_dispatches_a_duplicate_active_goal():
    route = load_route_plan("south_west_gallery", ROUTES_PATH, LAYOUT_PATH)
    sequence = GoalSequence(route)
    first = sequence.claim_next()
    with pytest.raises(RuntimeError, match="already active"):
        sequence.claim_next()
    sequence.finish_active("succeeded")
    assert sequence.claim_next() == route[1]
    assert first == route[0]


def test_paused_sequence_resumes_only_the_same_active_waypoint():
    route = load_route_plan("south_west_gallery", ROUTES_PATH, LAYOUT_PATH)
    sequence = GoalSequence(route)
    sequence.claim_next()
    sequence.finish_active("succeeded")
    current = sequence.claim_next()

    sequence.pause_active()
    assert sequence.resume_active() is current
    sequence.finish_active("succeeded")

    assert current is route[1]
    assert sequence.index == 2
    assert sequence.claim_next() is route[2]


def test_all_routes_use_serialized_to_pose_actions():
    assert route_action_kind(
        load_route_plan("central_gallery", ROUTES_PATH, LAYOUT_PATH)
    ) == "navigate_to_pose"
    for destination in ("south_west_gallery", "south_east_gallery"):
        route = load_route_plan(destination, ROUTES_PATH, LAYOUT_PATH)
        assert route_action_kind(route) == "navigate_to_pose"


def test_to_pose_tree_plans_once_and_preserves_recovery():
    root = ET.parse(ROUTE_BT_PATH).getroot()
    tags = [element.tag for element in root.iter()]
    assert tags.count("ComputePathToPose") == 1
    assert tags.count("FollowPath") == 1
    assert "RateController" not in tags
    assert tags.count("RecoveryNode") >= 3


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ("succeeded", "succeeded"),
        ("failed", "failed"),
        ("cancelled", "cancelled"),
    ],
)
def test_goal_sequence_handles_terminal_results(result, expected):
    route = load_route_plan("central_gallery", ROUTES_PATH, LAYOUT_PATH)
    sequence = GoalSequence(route)
    sequence.claim_next()
    sequence.finish_active(result)
    assert sequence.state == expected
    assert sequence.claim_next() is None


def test_localization_monitor_uses_synchronized_tf_not_amcl_topic_cadence():
    monitor = LocalizationMonitor(max_skew_sec=0.2)
    gazebo = TimedPose(1_000_000_000, 1.0, 2.0, 0.1)
    corrected = TimedPose(1_050_000_000, 1.01, 2.0, 0.1)
    localized_tf = TimedPose(1_000_000_000, 1.02, 2.0, 0.1)

    assert monitor.evaluate(gazebo, corrected, None) is None
    errors = monitor.evaluate(gazebo, corrected, localized_tf)
    assert errors is not None
    assert errors.corrected_gazebo_position == pytest.approx(0.01)
    assert errors.localized_gazebo_position == pytest.approx(0.02)
    assert monitor.consecutive_divergent == 0
    assert monitor.last_poses == (gazebo, corrected, localized_tf)


def test_scan_timestamp_can_wait_for_lagging_localization_tf():
    monitor = LocalizationMonitor(max_skew_sec=0.2)
    scan_stamp = 1_000_000_000
    gazebo = TimedPose(scan_stamp + 20_000_000, 1.0, 2.0, 0.1)
    corrected = TimedPose(scan_stamp, 1.01, 2.0, 0.1)

    assert monitor.evaluate(gazebo, corrected, None) is None
    delayed_tf = TimedPose(scan_stamp, 1.02, 2.0, 0.1)
    assert monitor.evaluate(gazebo, corrected, delayed_tf) is not None
    synchronized = monitor.last_poses
    assert synchronized is not None
    assert {pose.stamp_ns for pose in synchronized} == {
        scan_stamp,
        scan_stamp + 20_000_000,
    }


def test_route_acceptance_requires_terminal_not_every_intermediate_tf_sample():
    results = [
        {"name": "intermediate", "fresh_localization_tf": False},
        {"name": "candidate", "fresh_localization_tf": True},
    ]
    assert terminal_localization_is_fresh(results)
    assert not terminal_localization_is_fresh(results[:-1])
    assert not terminal_localization_is_fresh([])


def test_monitor_rejects_unsynchronized_poses_and_cancels_safely():
    monitor = LocalizationMonitor(
        max_skew_sec=0.1, divergence_limit_m=1.0, consecutive_limit=3
    )
    gazebo = TimedPose(1_000_000_000, 0.0, 0.0, 0.0)
    stale = TimedPose(2_000_000_000, 0.0, 0.0, 0.0)
    assert monitor.evaluate(gazebo, stale, gazebo) is None
    assert not monitor.cancellation_required

    divergent_tf = TimedPose(1_000_000_000, 1.1, 0.0, 0.0)
    for _ in range(3):
        monitor.evaluate(gazebo, gazebo, divergent_tf)
    assert monitor.cancellation_required


def test_runtime_map_reader_confirms_all_final_candidates_are_known_free():
    occupancy_map = TrinaryOccupancyMap(MAP_PATH)
    for destination in (
        "central_gallery",
        "north_gallery",
        "south_west_gallery",
        "south_east_gallery",
    ):
        target = load_route_plan(destination, ROUTES_PATH, LAYOUT_PATH)[-1]
        assert occupancy_map.is_known_free(target.x, target.y)


def test_acceptance_runner_uses_the_simulation_clock():
    source = ACCEPTANCE_SCRIPT.read_text(encoding="utf-8")
    invocation = source.split(
        "ros2 run museum_assistant supplied_museum_route_runner", 1
    )[1]
    assert "--ros-args -p use_sim_time:=true" in invocation


def test_route_timeouts_cover_the_measured_simulation_rotation_time():
    arguments = parse_args(
        ["--destination", "central_gallery", "--output", "/tmp/result.json"]
    )
    assert arguments.intermediate_timeout == 240.0
    assert arguments.final_timeout == 300.0
    assert arguments.waypoint_behavior_tree.name == (
        "supplied_museum_to_pose.xml"
    )
