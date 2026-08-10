import json
from pathlib import Path

import pytest

from museum_assistant.contracts import StructuredRequest
from museum_assistant.reasoning import DeterministicReasoner
from museum_assistant.semantic_graph import load_semantic_graph
from museum_assistant.semantic_route_dispatch import (
    ReasoningRouteDispatcher,
    SemanticRouteResolver,
)


PACKAGE = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE / "config"


@pytest.fixture
def graph():
    return load_semantic_graph(CONFIG / "semantic_map.yaml")


def request(constraints):
    return {
        "request_id": "scene_graph_test",
        "intent": "recommend_and_prepare_navigation",
        "constraints": constraints,
    }


def rejection_reasons(decision, room_id):
    return next(
        item["reasons"]
        for item in decision["rejected_rooms"]
        if item["room"] == room_id
    )


def test_artwork_room_reasoning_traverses_located_in_edge(graph):
    graph.artworks["monet_water_lilies"]["located_in"] = "kids_hall"
    graph.graph.nodes["monet_water_lilies"]["located_in"] = "kids_hall"

    decision = DeterministicReasoner(graph).handle_request(
        request({"style": "impressionism"})
    )

    assert decision["selected_room"] == "impressionism_hall"
    assert decision["matching_artworks"] == ["monet_water_lilies"]


def test_room_state_query_and_reasoning_read_graph_node(graph):
    graph.graph.nodes["impressionism_hall"]["crowd_level"] = "high"
    assert graph.rooms["impressionism_hall"]["crowd_level"] == "medium"

    decision = DeterministicReasoner(graph).handle_request(
        request({"style": "impressionism", "avoid_crowd": True})
    )

    assert graph.get_room_state("impressionism_hall")["crowd_level"] == "high"
    assert decision["status"] == "no_match"
    assert "crowd_level_high" in rejection_reasons(
        decision, "impressionism_hall"
    )


def test_dynamic_updates_change_next_decision_without_yaml_persistence(graph):
    reasoner = DeterministicReasoner(graph)
    semantic_map_text = (CONFIG / "semantic_map.yaml").read_text(encoding="utf-8")
    museum_request = request(
        {"style": "impressionism", "avoid_crowd": True}
    )

    before = reasoner.handle_request(museum_request)
    graph.update_room_state("impressionism_hall", crowd_level="high")
    after = reasoner.handle_request(museum_request)
    graph.update_room_state("impressionism_hall", crowd_level="low")
    reset = reasoner.handle_request(museum_request)

    assert before["selected_room"] == "impressionism_hall"
    assert after["status"] == "no_match"
    assert "crowd_level_high" in rejection_reasons(
        after, "impressionism_hall"
    )
    assert reset["selected_room"] == "impressionism_hall"
    assert (CONFIG / "semantic_map.yaml").read_text(
        encoding="utf-8"
    ) == semantic_map_text


def test_connected_to_neighbors_are_a_semantic_query(graph):
    assert graph.neighbors("main_corridor") == [
        "impressionism_hall",
        "ancient_art_hall",
        "kids_hall",
        "temporary_exhibition",
        "exit",
    ]
    assert graph.neighbors("monet_water_lilies", "located_in") == [
        "impressionism_hall"
    ]


def test_snapshot_is_compact_serializable_and_reflects_updates(graph):
    graph.update_room_state("ancient_art_hall", noise_level="high")
    snapshot = graph.snapshot()
    encoded = json.dumps(snapshot)
    room = next(
        node for node in snapshot["nodes"] if node["id"] == "ancient_art_hall"
    )

    assert encoded
    assert room["noise_level"] == "high"
    assert "nav_pose" not in room
    assert {
        "source": "monet_water_lilies",
        "relation": "located_in",
        "target": "impressionism_hall",
    } in snapshot["edges"]


def test_avoid_noise_contract_and_dynamic_rejection(graph):
    structured = StructuredRequest.from_dict(
        request({"style": "classical", "avoid_noise": True})
    )
    reasoner = DeterministicReasoner(graph)
    before = reasoner.decide(structured).to_dict()
    graph.update_room_state("ancient_art_hall", noise_level="high")
    after = reasoner.decide(structured).to_dict()

    assert before["selected_room"] == "ancient_art_hall"
    assert "low noise level" in before["reason"]
    assert after["status"] == "no_match"
    assert "noise_level_high" in rejection_reasons(
        after, "ancient_art_hall"
    )


def test_invalid_ambient_update_is_atomic(graph):
    before = graph.get_room_state("ancient_art_hall")
    with pytest.raises(ValueError, match="Invalid noise_level"):
        graph.update_room_state(
            "ancient_art_hall", status="closed", noise_level="extreme"
        )
    assert graph.get_room_state("ancient_art_hall") == before


def test_success_dispatches_and_dynamic_no_match_does_not(graph):
    resolver = SemanticRouteResolver.from_files(
        CONFIG / "supplied_museum_semantic_routes.yaml",
        graph,
        CONFIG / "supplied_museum_routes.yaml",
        CONFIG / "supplied_museum_room_layout.yaml",
    )
    dispatcher = ReasoningRouteDispatcher(resolver)
    reasoner = DeterministicReasoner(graph)

    success = reasoner.handle_request(request({"style": "classical"}))
    route_request, route_reason = dispatcher.prepare(success)
    graph.update_room_state("ancient_art_hall", status="closed")
    no_match = reasoner.handle_request(request({"style": "classical"}))
    blocked_request, blocked_reason = dispatcher.prepare(no_match)

    assert route_reason == "dispatched"
    assert route_request["route"] == "south_west_gallery"
    assert blocked_request is None
    assert blocked_reason == "decision_status_not_success"
    assert dispatcher.route_request_count == 1
