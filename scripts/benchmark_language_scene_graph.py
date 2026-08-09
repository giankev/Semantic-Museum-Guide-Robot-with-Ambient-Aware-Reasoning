#!/usr/bin/env python3
"""Bounded offline functional benchmark for the text-language pipeline."""

import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "exchange/museum_ws/src/museum_assistant"
CONFIG = PACKAGE / "config"
sys.path.insert(0, str(PACKAGE))

from museum_assistant.language_parser import (  # noqa: E402
    parse_deterministic,
    route_text,
)
from museum_assistant.reasoning import DeterministicReasoner  # noqa: E402
from museum_assistant.semantic_graph import load_semantic_graph  # noqa: E402
from museum_assistant.semantic_route_dispatch import (  # noqa: E402
    ReasoningRouteDispatcher,
    SemanticRouteResolver,
)


def case(
    name,
    text,
    intent=None,
    constraints=None,
    room=None,
    updates=None,
    rejection=None,
    direct=False,
):
    return {
        "name": name,
        "text": text,
        "intent": intent,
        "constraints": constraints or {},
        "room": room,
        "updates": updates or {},
        "rejection": rejection,
        "direct": direct,
    }


NAV = "recommend_and_prepare_navigation"
REC = "recommend"
CASES = (
    case("it_nav_impressionism", "Portami a vedere arte impressionista", NAV,
         {"style": "impressionism"}, "impressionism_hall"),
    case("en_nav_impressionism", "Take me to impressionist art", NAV,
         {"style": "impressionism"}, "impressionism_hall"),
    case("it_rec_impressionism", "Consigliami qualcosa di impressionista", REC,
         {"style": "impressionism"}, "impressionism_hall"),
    case("en_rec_impressionism", "Recommend impressionist art", REC,
         {"style": "impressionism"}, "impressionism_hall"),
    case("it_rec_classical", "Consigliami qualcosa di classico", REC,
         {"style": "classical"}, "ancient_art_hall"),
    case("en_nav_classical", "Guide me to classical art", NAV,
         {"style": "classical"}, "ancient_art_hall"),
    case("it_children", "Consigliami qualcosa per bambini", REC,
         {"child_friendly": True}, "kids_hall"),
    case("en_children", "Take me somewhere child friendly", NAV,
         {"child_friendly": True}, "kids_hall"),
    case("it_accessible", "Consigliami una sala accessibile", REC,
         {"wheelchair_accessible": True}, "ancient_art_hall"),
    case("en_accessible", "Take me somewhere wheelchair accessible", NAV,
         {"wheelchair_accessible": True}, "ancient_art_hall"),
    case("it_avoid_crowd", "Vorrei qualcosa non affollato", REC,
         {"avoid_crowd": True}, "ancient_art_hall"),
    case("en_avoid_crowd", "I prefer something not crowded", REC,
         {"avoid_crowd": True}, "ancient_art_hall"),
    case("it_quiet_room", "Vorrei una sala tranquilla", REC,
         {"avoid_noise": True}, "ancient_art_hall"),
    case("it_avoid_noisy", "Evita le sale rumorose", REC,
         {"avoid_noise": True}, "ancient_art_hall"),
    case("it_silent_place", "Preferisco un posto silenzioso", REC,
         {"avoid_noise": True}, "ancient_art_hall"),
    case("en_avoid_noisy", "Avoid noisy rooms", REC,
         {"avoid_noise": True}, "ancient_art_hall"),
    case("en_quiet_place", "I prefer somewhere quiet", REC,
         {"avoid_noise": True}, "ancient_art_hall"),
    case("en_nav_quiet", "Take me somewhere quiet", NAV,
         {"avoid_noise": True}, "ancient_art_hall"),
    case(
        "it_combined",
        "Portami a vedere arte impressionista evitando folla e rumore",
        NAV,
        {"style": "impressionism", "avoid_crowd": True,
         "avoid_noise": True},
        "impressionism_hall",
    ),
    case(
        "en_combined",
        "Take me to impressionist art, avoid crowds and noisy rooms",
        NAV,
        {"style": "impressionism", "avoid_crowd": True,
         "avoid_noise": True},
        "impressionism_hall",
    ),
    case(
        "dynamic_noise_high",
        "Portami a vedere qualcosa di impressionista in una sala tranquilla",
        NAV,
        {"style": "impressionism", "avoid_noise": True},
        updates={"impressionism_hall": {"noise_level": "high"}},
        rejection="noise_level_high",
    ),
    case(
        "dynamic_crowd_high",
        "Portami a vedere qualcosa di impressionista evitando folla e rumore",
        NAV,
        {"style": "impressionism", "avoid_crowd": True,
         "avoid_noise": True},
        updates={"impressionism_hall": {"crowd_level": "high"}},
        rejection="crowd_level_high",
    ),
    case("direct_forward", "Move forward one metre", direct=True),
    case("direct_coordinates", "Drive directly to x=100 y=200", direct=True),
    case("unresolved", "Open the cafe after midnight"),
    case("empty", ""),
    case("direct_italian", "Vai avanti", direct=True),
)


def fake_direct_candidate(_text):
    return json.dumps(
        {"resolved": True, "intent": NAV, "constraints": {}}
    )


def make_dispatcher(graph):
    resolver = SemanticRouteResolver.from_files(
        CONFIG / "supplied_museum_semantic_routes.yaml",
        graph,
        CONFIG / "supplied_museum_routes.yaml",
        CONFIG / "supplied_museum_room_layout.yaml",
    )
    return ReasoningRouteDispatcher(resolver)


def run_case(definition):
    parsed = parse_deterministic(definition["text"])
    expected_resolved = definition["intent"] is not None
    parser_correct = (parsed is not None) == expected_resolved
    intent_correct = (
        not expected_resolved
        or (parsed is not None and parsed["intent"] == definition["intent"])
    )
    constraints_correct = (
        not expected_resolved
        or (
            parsed is not None
            and parsed["constraints"] == definition["constraints"]
        )
    )

    routed = route_text(
        definition["text"],
        request_id=definition["name"],
        llm_callable=(fake_direct_candidate if definition["direct"] else None),
    )
    invalid_rejected = expected_resolved or routed.request is None
    decision_correct = True
    route_policy_correct = True
    decision = None
    if routed.request is not None:
        graph = load_semantic_graph(CONFIG / "semantic_map.yaml")
        for room_id, state in definition["updates"].items():
            graph.update_room_state(room_id, **state)
        decision = DeterministicReasoner(graph).decide(routed.request).to_dict()
        expected_status = "no_match" if definition["rejection"] else "success"
        decision_correct = (
            decision["status"] == expected_status
            and decision["selected_room"] == definition["room"]
            and (
                definition["rejection"] is None
                or any(
                    definition["rejection"] in rejected["reasons"]
                    for rejected in decision["rejected_rooms"]
                )
            )
        )
        route_request, _ = make_dispatcher(graph).prepare(decision)
        should_route = definition["intent"] == NAV and expected_status == "success"
        route_policy_correct = (route_request is not None) == should_route

    return {
        "name": definition["name"],
        "parser_correct": parser_correct,
        "intent_correct": intent_correct,
        "constraints_correct": constraints_correct,
        "invalid_rejected": invalid_rejected,
        "decision_correct": decision_correct,
        "route_policy_correct": route_policy_correct,
        "route_status": routed.status,
        "decision": decision,
    }


def main():
    results = [run_case(definition) for definition in CASES]
    resolved = [
        result for result, definition in zip(results, CASES)
        if definition["intent"] is not None
    ]
    invalid = [
        result for result, definition in zip(results, CASES)
        if definition["intent"] is None
    ]
    summary = {
        "benchmark": "bounded functional language benchmark",
        "number_phrases": len(results),
        "parser_resolved_correctly": sum(r["parser_correct"] for r in results),
        "intent_accuracy": sum(r["intent_correct"] for r in resolved) / len(resolved),
        "constraint_extraction_accuracy": (
            sum(r["constraints_correct"] for r in resolved) / len(resolved)
        ),
        "invalid_direct_rejection": sum(r["invalid_rejected"] for r in invalid),
        "invalid_direct_cases": len(invalid),
        "end_to_end_reasoning_correct": sum(
            r["decision_correct"] for r in resolved
        ),
        "end_to_end_reasoning_cases": len(resolved),
        "route_policy_correct": sum(r["route_policy_correct"] for r in resolved),
    }
    print(json.dumps({"summary": summary, "cases": results}, indent=2))
    expected = len(results) + 4 * len(resolved) + len(invalid)
    actual = (
        summary["parser_resolved_correctly"]
        + sum(r["intent_correct"] for r in resolved)
        + sum(r["constraints_correct"] for r in resolved)
        + summary["invalid_direct_rejection"]
        + summary["end_to_end_reasoning_correct"]
        + summary["route_policy_correct"]
    )
    if actual != expected:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
