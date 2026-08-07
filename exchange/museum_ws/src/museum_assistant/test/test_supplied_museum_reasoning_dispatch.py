from copy import deepcopy
from pathlib import Path

import pytest
import yaml

from museum_assistant.semantic_graph import load_semantic_graph
from museum_assistant.semantic_route_dispatch import (
    ReasoningRouteDispatcher,
    SemanticRouteConfigurationError,
    SemanticRouteResolver,
)
from museum_assistant.supplied_museum_route_runner import (
    correlated_navigation_result,
)


REPO_ROOT = Path(__file__).resolve().parents[5]
PACKAGE = REPO_ROOT / "exchange/museum_ws/src/museum_assistant"
SEMANTIC_MAP = PACKAGE / "config/semantic_map.yaml"
MAPPING = PACKAGE / "config/supplied_museum_semantic_routes.yaml"
ROUTES = PACKAGE / "config/supplied_museum_routes.yaml"
LAYOUT = PACKAGE / "config/supplied_museum_room_layout.yaml"
LAUNCH = PACKAGE / "launch/supplied_museum_reasoning_navigation.launch.py"
DISPATCH_NODE = (
    PACKAGE / "museum_assistant/semantic_route_dispatcher_node.py"
)


@pytest.fixture
def graph():
    return load_semantic_graph(SEMANTIC_MAP)


@pytest.fixture
def resolver(graph):
    return SemanticRouteResolver.from_files(
        MAPPING, graph, ROUTES, LAYOUT
    )


def executable_decision(room="impressionism_hall"):
    return {
        "request_id": "request_1",
        "session_id": "session_1",
        "status": "success",
        "skill": "navigate_to",
        "selected_room": room,
    }


def write_yaml(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")
    return path


def test_required_semantic_rooms_map_to_validated_physical_routes(resolver):
    expected = {
        "impressionism_hall": "north_gallery",
        "ancient_art_hall": "south_west_gallery",
        "kids_hall": "south_east_gallery",
    }
    assert {
        room: resolver.resolve(room).route for room in expected
    } == expected


def test_nonexistent_semantic_room_fails_startup_validation(
    graph, tmp_path
):
    mapping = yaml.safe_load(MAPPING.read_text(encoding="utf-8"))
    mapping["semantic_routes"]["missing_semantic_room"] = {
        "physical_room": "north_gallery",
        "route": "north_gallery",
    }
    path = write_yaml(tmp_path, "mapping.yaml", mapping)
    with pytest.raises(
        SemanticRouteConfigurationError, match="Unknown semantic room"
    ):
        SemanticRouteResolver.from_files(path, graph, ROUTES, LAYOUT)


def test_nonexistent_route_fails_startup_validation(graph, tmp_path):
    routes = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    del routes["routes"]["north_gallery"]
    path = write_yaml(tmp_path, "routes.yaml", routes)
    with pytest.raises(
        SemanticRouteConfigurationError, match="route 'north_gallery' is missing"
    ):
        SemanticRouteResolver.from_files(MAPPING, graph, path, LAYOUT)


def test_unknown_and_duplicate_route_waypoints_fail_validation(
    graph, tmp_path
):
    routes = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    routes["routes"]["north_gallery"] = ["missing_waypoint"]
    missing = write_yaml(tmp_path, "missing.yaml", routes)
    with pytest.raises(
        SemanticRouteConfigurationError, match="unknown route waypoint"
    ):
        SemanticRouteResolver.from_files(MAPPING, graph, missing, LAYOUT)

    routes = yaml.safe_load(ROUTES.read_text(encoding="utf-8"))
    routes["routes"]["south_west_gallery"].insert(1, "south_entry")
    duplicate = write_yaml(tmp_path, "duplicate.yaml", routes)
    with pytest.raises(
        SemanticRouteConfigurationError, match="duplicate waypoint"
    ):
        SemanticRouteResolver.from_files(MAPPING, graph, duplicate, LAYOUT)


def test_route_cannot_end_in_a_different_physical_room(graph, tmp_path):
    layout = yaml.safe_load(LAYOUT.read_text(encoding="utf-8"))
    layout["candidate_poses"]["candidate_north"]["area"] = (
        "south_west_gallery"
    )
    path = write_yaml(tmp_path, "layout.yaml", layout)
    with pytest.raises(
        SemanticRouteConfigurationError, match="ends in"
    ):
        SemanticRouteResolver.from_files(MAPPING, graph, ROUTES, path)


def test_no_match_and_non_executable_skill_do_not_dispatch(resolver):
    dispatcher = ReasoningRouteDispatcher(resolver)
    no_match = executable_decision()
    no_match["status"] = "no_match"
    assert dispatcher.prepare(no_match).reason == (
        "decision_status_not_success"
    )

    clarification = executable_decision()
    clarification["skill"] = "ask_clarification"
    assert dispatcher.prepare(clarification).reason == "skill_not_executable"
    assert dispatcher.route_request_count == 0


def test_duplicate_decision_is_rejected_and_never_double_dispatches(resolver):
    dispatcher = ReasoningRouteDispatcher(resolver)
    decision = executable_decision()
    first = dispatcher.prepare(decision)
    second = dispatcher.prepare(deepcopy(decision))
    assert first.dispatched
    assert not second.dispatched
    assert second.reason == "duplicate_decision"
    assert dispatcher.route_request_count == 1


def test_unknown_selected_room_is_rejected(resolver):
    dispatcher = ReasoningRouteDispatcher(resolver)
    outcome = dispatcher.prepare(executable_decision("temporary_exhibition"))
    assert not outcome.dispatched
    assert outcome.reason == "unknown_semantic_route"


def test_route_request_propagates_all_correlation_fields(resolver):
    request = ReasoningRouteDispatcher(resolver).prepare(
        executable_decision("ancient_art_hall")
    ).route_request
    assert request is not None
    assert request["request_id"] == "request_1"
    assert request["session_id"] == "session_1"
    assert request["selected_room"] == "ancient_art_hall"
    assert request["route"] == "south_west_gallery"


def test_final_candidate_is_correct_for_every_semantic_room(resolver):
    expected = {
        "impressionism_hall": "candidate_north",
        "ancient_art_hall": "candidate_south_west",
        "kids_hall": "candidate_south_east",
    }
    assert {
        room: resolver.resolve(room).final_candidate for room in expected
    } == expected


def test_both_southern_routes_are_complete(resolver):
    common = ("south_entry", "south_junction", "south_inner_gap")
    west = resolver.resolve("ancient_art_hall").waypoint_names
    east = resolver.resolve("kids_hall").waypoint_names
    assert west == common + (
        "south_west_door_approach",
        "candidate_south_west",
    )
    assert east == common + (
        "south_east_door_approach",
        "candidate_south_east",
    )


def test_dispatch_layer_has_no_nav2_action_client_and_launch_has_one_runner():
    dispatch_source = DISPATCH_NODE.read_text(encoding="utf-8")
    launch_source = LAUNCH.read_text(encoding="utf-8")
    assert "ActionClient" not in dispatch_source
    assert "NavigateToPose" not in dispatch_source
    assert "semantic_navigation_node" not in launch_source
    assert launch_source.count('executable="supplied_museum_route_runner_node"') == 1


def test_terminal_result_is_correlated_and_requires_the_final_candidate():
    route_request = {
        "request_id": "request_1",
        "session_id": "session_1",
        "selected_room": "impressionism_hall",
        "route": "north_gallery",
        "final_candidate": "candidate_north",
    }
    report = {
        "status": "passed",
        "goal_uuids": ["goal_1"],
        "checks": {"all_nav2_goals_succeeded": True},
        "final": {
            "target": {"name": "candidate_north"},
            "gazebo_target_error_m": 0.25,
        },
    }
    result = correlated_navigation_result(route_request, report)
    assert result["status"] == "succeeded"
    assert result["candidate_reached"] is True
    assert result["request_id"] == "request_1"
    assert result["session_id"] == "session_1"
    assert result["selected_room"] == "impressionism_hall"

    report["final"]["target"]["name"] = "south_inner_gap"
    assert correlated_navigation_result(route_request, report)["status"] == (
        "failed"
    )
