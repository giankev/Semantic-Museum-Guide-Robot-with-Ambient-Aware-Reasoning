from pathlib import Path

from museum_assistant.language_parser import route_text
from museum_assistant.reasoning import DeterministicReasoner
from museum_assistant.semantic_graph import load_semantic_graph
from museum_assistant.semantic_route_dispatch import (
    ReasoningRouteDispatcher,
    SemanticRouteResolver,
)


PACKAGE = Path(__file__).resolve().parents[1]
CONFIG = PACKAGE / "config"
QUIET_IMPRESSIONISM = (
    "Portami a vedere qualcosa di impressionista in una sala tranquilla"
)


def make_pipeline():
    graph = load_semantic_graph(CONFIG / "semantic_map.yaml")
    reasoner = DeterministicReasoner(graph)
    resolver = SemanticRouteResolver.from_files(
        CONFIG / "supplied_museum_semantic_routes.yaml",
        graph,
        CONFIG / "supplied_museum_routes.yaml",
        CONFIG / "supplied_museum_room_layout.yaml",
    )
    return graph, reasoner, ReasoningRouteDispatcher(resolver)


def decide(reasoner, text, request_id):
    routed = route_text(text, request_id=request_id)
    assert routed.request is not None
    return routed.request, reasoner.decide(routed.request).to_dict()


def room_rejections(decision, room_id):
    return next(
        rejected["reasons"]
        for rejected in decision["rejected_rooms"]
        if rejected["room"] == room_id
    )


def test_same_text_tracks_dynamic_noise_and_route_dispatch():
    graph, reasoner, dispatcher = make_pipeline()
    graph.update_room_state("impressionism_hall", noise_level="low")

    request_a, decision_a = decide(reasoner, QUIET_IMPRESSIONISM, "language_a")
    route_a, reason_a = dispatcher.prepare(decision_a)
    graph.update_room_state("impressionism_hall", noise_level="high")
    request_b, decision_b = decide(reasoner, QUIET_IMPRESSIONISM, "language_b")
    route_b, reason_b = dispatcher.prepare(decision_b)
    graph.update_room_state("impressionism_hall", noise_level="low")
    _, decision_c = decide(reasoner, QUIET_IMPRESSIONISM, "language_c")

    assert request_a.constraints == request_b.constraints == {
        "style": "impressionism",
        "avoid_noise": True,
    }
    assert decision_a["selected_room"] == "impressionism_hall"
    assert reason_a == "dispatched"
    assert route_a["route"] == "north_gallery"
    assert decision_b["status"] == "no_match"
    assert "noise_level_high" in room_rejections(
        decision_b, "impressionism_hall"
    )
    assert route_b is None
    assert reason_b == "decision_status_not_success"
    assert decision_c["selected_room"] == "impressionism_hall"


def test_combined_language_constraints_reject_high_crowd():
    graph, reasoner, dispatcher = make_pipeline()
    graph.update_room_state("impressionism_hall", crowd_level="high")
    request, decision = decide(
        reasoner,
        "Portami a vedere qualcosa di impressionista evitando folla e rumore",
        "language_d",
    )

    assert request.constraints == {
        "style": "impressionism",
        "avoid_crowd": True,
        "avoid_noise": True,
    }
    assert decision["status"] == "no_match"
    assert "crowd_level_high" in room_rejections(
        decision, "impressionism_hall"
    )
    assert dispatcher.prepare(decision)[0] is None


def test_recommendation_selects_room_but_never_dispatches_route():
    _, reasoner, dispatcher = make_pipeline()
    request, decision = decide(
        reasoner,
        "Consigliami qualcosa di classico",
        "language_e",
    )

    assert request.intent == "recommend"
    assert request.constraints == {"style": "classical"}
    assert decision["selected_room"] == "ancient_art_hall"
    assert dispatcher.prepare(decision) == (None, "intent_not_executable")
