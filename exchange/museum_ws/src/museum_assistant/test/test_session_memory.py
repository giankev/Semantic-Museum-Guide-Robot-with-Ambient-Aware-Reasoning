from pathlib import Path

import pytest

from museum_assistant.language_parser import parse_deterministic, route_text
from museum_assistant.reasoning import DeterministicReasoner
from museum_assistant.semantic_graph import load_semantic_graph
from museum_assistant.semantic_route_dispatch import (
    ReasoningRouteDispatcher,
    SemanticRouteResolver,
)


PACKAGE = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE / "config"


@pytest.fixture
def pipeline():
    graph = load_semantic_graph(CONFIG / "semantic_map.yaml")
    resolver = SemanticRouteResolver.from_files(
        CONFIG / "supplied_museum_semantic_routes.yaml",
        graph,
        CONFIG / "supplied_museum_routes.yaml",
        CONFIG / "supplied_museum_room_layout.yaml",
    )
    return graph, DeterministicReasoner(graph), ReasoningRouteDispatcher(resolver)


def decide(reasoner, text, request_id, session_id):
    routed = route_text(text, request_id=request_id, session_id=session_id)
    assert routed.request is not None
    return reasoner.decide(routed.request).to_dict()


@pytest.mark.parametrize(
    "text",
    ("Ok, portami lì", "Portami lì", "Take me there", "Guide me there"),
)
def test_deictic_language_is_already_navigation_without_constraints(text):
    assert parse_deterministic(text) == {
        "resolved": True,
        "intent": "recommend_and_prepare_navigation",
        "constraints": {},
    }


def test_ros_light_follow_up_snapshot_and_single_route(pipeline):
    graph, reasoner, dispatcher = pipeline
    recommendation = decide(
        reasoner,
        "Vorrei vedere impressionismo evitando la folla",
        "turn_1",
        "session_1",
    )
    assert dispatcher.prepare(recommendation)[0] is None

    context = graph.get_session_context("session_1")
    assert context["preferred_style"] == "impressionism"
    assert context["avoid_crowd"] is True
    assert context["wants_to_reach"] == "impressionism_hall"
    snapshot = graph.snapshot()
    assert {
        "id": "session_1",
        "kind": "session",
        "session_id": "session_1",
        "active": True,
        "preferred_style": "impressionism",
        "avoid_crowd": True,
        "last_intent": "recommend",
        "interaction_state": "recommended",
    } in snapshot["nodes"]
    assert {
        "source": "session_1",
        "relation": "wants_to_reach",
        "target": "impressionism_hall",
    } in snapshot["edges"]

    follow_up = decide(
        reasoner, "Ok, portami lì", "turn_2", "session_1"
    )
    route, status = dispatcher.prepare(follow_up)
    assert follow_up["selected_room"] == "impressionism_hall"
    assert status == "dispatched"
    assert route["route"] == "north_gallery"
    assert dispatcher.route_request_count == 1

    no_memory = decide(
        reasoner, "Portami lì", "turn_3", "session_2"
    )
    assert no_memory["status"] == "no_match"
    assert no_memory["skill"] == "ask_clarification"
    assert dispatcher.prepare(no_memory)[0] is None
    assert dispatcher.route_request_count == 1


def test_explicit_request_replaces_destination_and_preferences(pipeline):
    graph, reasoner, dispatcher = pipeline
    decide(
        reasoner,
        "Consigliami impressionismo evitando la folla",
        "first",
        "session_1",
    )
    decide(
        reasoner,
        "Consigliami qualcosa di classico",
        "override",
        "session_1",
    )
    context = graph.get_session_context("session_1")
    assert context["preferred_style"] == "classical"
    assert "avoid_crowd" not in context
    assert context["wants_to_reach"] == "ancient_art_hall"

    follow_up = decide(reasoner, "Portami lì", "follow", "session_1")
    route, _ = dispatcher.prepare(follow_up)
    assert follow_up["selected_room"] == "ancient_art_hall"
    assert route["route"] == "south_west_gallery"


def test_follow_up_revalidates_ambient_state_and_recovers(pipeline):
    graph, reasoner, dispatcher = pipeline
    decide(
        reasoner,
        "Consigliami impressionismo evitando la folla",
        "recommend",
        "session_1",
    )
    graph.update_room_state("impressionism_hall", crowd_level="high")
    blocked = decide(reasoner, "Portami lì", "blocked", "session_1")
    reasons = blocked["rejected_rooms"][0]["reasons"]
    assert blocked["status"] == "no_match"
    assert "crowd_level_high" in reasons
    assert dispatcher.prepare(blocked)[0] is None

    graph.update_room_state("impressionism_hall", crowd_level="low")
    resumed = decide(reasoner, "Portami lì", "resumed", "session_1")
    route, _ = dispatcher.prepare(resumed)
    assert resumed["selected_room"] == "impressionism_hall"
    assert route["route"] == "north_gallery"
