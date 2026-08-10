#!/usr/bin/env python3
"""Offline functional benchmark for deterministic scene-graph reasoning."""

import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "exchange/museum_ws/src/museum_assistant"
CONFIG = PACKAGE / "config"
sys.path.insert(0, str(PACKAGE))

from museum_assistant.reasoning import DeterministicReasoner  # noqa: E402
from museum_assistant.semantic_graph import load_semantic_graph  # noqa: E402
from museum_assistant.semantic_route_dispatch import (  # noqa: E402
    ReasoningRouteDispatcher,
    SemanticRouteResolver,
)


CASES = (
    (
        "impressionism",
        {"style": "impressionism"},
        {},
        "impressionism_hall",
        None,
    ),
    ("classical", {"style": "classical"}, {}, "ancient_art_hall", None),
    ("children", {"child_friendly": True}, {}, "kids_hall", None),
    (
        "wheelchair",
        {"wheelchair_accessible": True},
        {},
        "ancient_art_hall",
        None,
    ),
    (
        "missing_style",
        {"style": "surrealist_clockwork"},
        {},
        None,
        "no_artwork_matching_style",
    ),
    (
        "crowd_medium",
        {"style": "impressionism", "avoid_crowd": True},
        {"impressionism_hall": {"crowd_level": "medium"}},
        "impressionism_hall",
        None,
    ),
    (
        "crowd_high",
        {"style": "impressionism", "avoid_crowd": True},
        {"impressionism_hall": {"crowd_level": "high"}},
        None,
        "crowd_level_high",
    ),
    (
        "crowd_reset_low",
        {"style": "impressionism", "avoid_crowd": True},
        {"impressionism_hall": {"crowd_level": "low"}},
        "impressionism_hall",
        None,
    ),
    (
        "classical_open",
        {"style": "classical"},
        {"ancient_art_hall": {"status": "open"}},
        "ancient_art_hall",
        None,
    ),
    (
        "classical_closed",
        {"style": "classical"},
        {"ancient_art_hall": {"status": "closed"}},
        None,
        "room_closed",
    ),
    (
        "classical_reopened",
        {"style": "classical"},
        {"ancient_art_hall": {"status": "open"}},
        "ancient_art_hall",
        None,
    ),
    (
        "noise_low",
        {"style": "classical", "avoid_noise": True},
        {"ancient_art_hall": {"noise_level": "low"}},
        "ancient_art_hall",
        None,
    ),
    (
        "noise_high",
        {"style": "classical", "avoid_noise": True},
        {"ancient_art_hall": {"noise_level": "high"}},
        None,
        "noise_level_high",
    ),
    (
        "noise_reset_low",
        {"style": "classical", "avoid_noise": True},
        {"ancient_art_hall": {"noise_level": "low"}},
        "ancient_art_hall",
        None,
    ),
    ("interactive", {"style": "interactive"}, {}, "kids_hall", None),
    (
        "interactive_crowded",
        {"style": "interactive", "avoid_crowd": True},
        {},
        None,
        "crowd_level_high",
    ),
    (
        "interactive_crowd_low",
        {"style": "interactive", "avoid_crowd": True},
        {"kids_hall": {"crowd_level": "low"}},
        "kids_hall",
        None,
    ),
    (
        "post_impressionism",
        {"style": "post_impressionism"},
        {},
        "impressionism_hall",
        None,
    ),
    ("ancient_egyptian", {"style": "ancient_egyptian"}, {}, "ancient_art_hall", None),
    ("adult_room", {"child_friendly": False}, {}, "ancient_art_hall", None),
    (
        "accessible_uncrowded",
        {"wheelchair_accessible": True, "avoid_crowd": True},
        {},
        "ancient_art_hall",
        None,
    ),
    (
        "impressionism_noisy",
        {"style": "impressionism", "avoid_noise": True},
        {"impressionism_hall": {"noise_level": "high"}},
        None,
        "noise_level_high",
    ),
    (
        "impressionism_noise_medium",
        {"style": "impressionism", "avoid_noise": True},
        {"impressionism_hall": {"noise_level": "medium"}},
        "impressionism_hall",
        None,
    ),
    (
        "normalized_style",
        {"style": "Impressionism"},
        {},
        "impressionism_hall",
        None,
    ),
    (
        "combined_constraints",
        {
            "style": "classical",
            "avoid_crowd": True,
            "avoid_noise": True,
            "wheelchair_accessible": True,
        },
        {},
        "ancient_art_hall",
        None,
    ),
)


def run_case(case):
    name, constraints, updates, expected_room, expected_rejection = case
    graph = load_semantic_graph(CONFIG / "semantic_map.yaml")
    for room_id, state in updates.items():
        graph.update_room_state(room_id, **state)
    reasoner = DeterministicReasoner(graph)
    decision = reasoner.handle_request(
        {
            "request_id": name,
            "session_id": "offline_benchmark",
            "intent": "recommend_and_prepare_navigation",
            "constraints": constraints,
        }
    )
    expected_status = "success" if expected_room else "no_match"
    decision_correct = (
        decision["status"] == expected_status
        and decision["selected_room"] == expected_room
    )
    rejection_correct = True
    if expected_rejection:
        rejection_correct = any(
            expected_rejection in rejected["reasons"]
            for rejected in decision["rejected_rooms"]
        )

    resolver = SemanticRouteResolver.from_files(
        CONFIG / "supplied_museum_semantic_routes.yaml",
        graph,
        CONFIG / "supplied_museum_routes.yaml",
        CONFIG / "supplied_museum_room_layout.yaml",
    )
    route_request, _ = ReasoningRouteDispatcher(resolver).prepare(decision)
    integration_correct = (
        route_request is not None
        if expected_status == "success"
        else route_request is None
    )
    return {
        "name": name,
        "status": decision["status"],
        "selected_room": decision["selected_room"],
        "decision_correct": decision_correct,
        "rejection_correct": rejection_correct,
        "integration_correct": integration_correct,
        "decision": decision,
    }


def main():
    first_run = [run_case(case) for case in CASES]
    second_run = [run_case(case) for case in CASES]
    repeated = all(
        first["decision"] == second["decision"]
        for first, second in zip(first_run, second_run)
    )
    no_match_results = [
        result for result in first_run if result["status"] == "no_match"
    ]
    rejection_results = [
        result
        for result, case in zip(first_run, CASES)
        if case[4] is not None
    ]
    summary = {
        "benchmark": "deterministic functional reasoner benchmark",
        "number_cases": len(first_run),
        "correct_decisions": sum(r["decision_correct"] for r in first_run),
        "decision_accuracy": (
            sum(r["decision_correct"] for r in first_run) / len(first_run)
        ),
        "correct_no_match": sum(
            r["decision_correct"] for r in no_match_results
        ),
        "no_match_cases": len(no_match_results),
        "correct_rejection_reason": sum(
            r["rejection_correct"] for r in rejection_results
        ),
        "rejection_reason_cases": len(rejection_results),
        "correct_route_integration": sum(
            r["integration_correct"] for r in first_run
        ),
        "deterministic_repeatability": repeated,
    }
    print(json.dumps({"summary": summary, "cases": first_run}, indent=2))
    if not (
        summary["correct_decisions"] == summary["number_cases"]
        and summary["correct_rejection_reason"]
        == summary["rejection_reason_cases"]
        and summary["correct_route_integration"] == summary["number_cases"]
        and repeated
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
