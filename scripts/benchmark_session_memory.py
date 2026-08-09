#!/usr/bin/env python3
"""Bounded functional benchmark for scene-graph session memory."""

import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE = REPO_ROOT / "exchange/museum_ws/src/museum_assistant"
CONFIG = PACKAGE / "config"
sys.path.insert(0, str(PACKAGE))

from museum_assistant.language_parser import route_text  # noqa: E402
from museum_assistant.reasoning import DeterministicReasoner  # noqa: E402
from museum_assistant.semantic_graph import load_semantic_graph  # noqa: E402
from museum_assistant.semantic_route_dispatch import (  # noqa: E402
    ReasoningRouteDispatcher,
    SemanticRouteResolver,
)


def pipeline():
    graph = load_semantic_graph(CONFIG / "semantic_map.yaml")
    resolver = SemanticRouteResolver.from_files(
        CONFIG / "supplied_museum_semantic_routes.yaml",
        graph,
        CONFIG / "supplied_museum_routes.yaml",
        CONFIG / "supplied_museum_room_layout.yaml",
    )
    return graph, DeterministicReasoner(graph), ReasoningRouteDispatcher(resolver)


def execute(reasoner, dispatcher, text, request_id, session_id):
    routed = route_text(text, request_id=request_id, session_id=session_id)
    assert routed.request is not None
    decision = reasoner.decide(routed.request).to_dict()
    route, route_status = dispatcher.prepare(decision)
    return decision, route, route_status


def rejection_reasons(decision):
    return sorted(
        reason
        for room in decision.get("rejected_rooms", [])
        for reason in room.get("reasons", [])
    )


def result(
    case_id,
    category,
    decision,
    route,
    *,
    expected_status,
    expected_room=None,
    expected_route=None,
    expected_rejection=None,
    memory_correct=None,
):
    decision_correct = (
        decision["status"] == expected_status
        and decision["selected_room"] == expected_room
    )
    rejection_correct = (
        expected_rejection is None
        or expected_rejection in rejection_reasons(decision)
    )
    route_policy_correct = (
        (route is None and expected_route is None)
        or (route is not None and route.get("route") == expected_route)
    )
    checks = [decision_correct, rejection_correct, route_policy_correct]
    if memory_correct is not None:
        checks.append(memory_correct)
    return {
        "case_id": case_id,
        "category": category,
        "expected_status": expected_status,
        "observed_status": decision["status"],
        "expected_room": expected_room,
        "predicted_room": decision["selected_room"],
        "expected_rejection": expected_rejection,
        "predicted_rejection": rejection_reasons(decision),
        "expected_route": expected_route,
        "predicted_route": route.get("route") if route else None,
        "memory_write_correct": memory_correct,
        "decision_correct": decision_correct,
        "route_policy_correct": route_policy_correct,
        "passed": all(checks),
    }


def run_benchmark():
    graph, reasoner, dispatcher = pipeline()
    results = []

    decision, route, _ = execute(
        reasoner,
        dispatcher,
        "Vorrei vedere impressionismo evitando la folla",
        "s1_recommend",
        "session_1",
    )
    context = graph.get_session_context("session_1")
    snapshot = graph.snapshot()
    memory_correct = (
        context["preferred_style"] == "impressionism"
        and context["avoid_crowd"] is True
        and context["wants_to_reach"] == "impressionism_hall"
        and {
            "source": "session_1",
            "relation": "wants_to_reach",
            "target": "impressionism_hall",
        }
        in snapshot["edges"]
    )
    results.append(result(
        "S1", "memory_write", decision, route,
        expected_status="success", expected_room="impressionism_hall",
        memory_correct=memory_correct,
    ))

    decision, route, _ = execute(
        reasoner, dispatcher, "Ok, portami lì", "s2_follow", "session_1"
    )
    results.append(result(
        "S2", "follow_up", decision, route,
        expected_status="success", expected_room="impressionism_hall",
        expected_route="north_gallery",
    ))

    decision, route, _ = execute(
        reasoner, dispatcher, "Portami lì", "s3_missing", None
    )
    results.append(result(
        "S3", "follow_up", decision, route, expected_status="no_match",
    ))

    decision, route, _ = execute(
        reasoner, dispatcher, "Portami lì", "s4_isolation", "session_2"
    )
    results.append(result(
        "S4", "session_isolation", decision, route,
        expected_status="no_match",
    ))

    execute(
        reasoner, dispatcher, "Consigliami qualcosa di classico",
        "s5_override", "session_1",
    )
    decision, route, _ = execute(
        reasoner, dispatcher, "Portami lì", "s5_follow", "session_1"
    )
    context = graph.get_session_context("session_1")
    results.append(result(
        "S5", "explicit_override", decision, route,
        expected_status="success", expected_room="ancient_art_hall",
        expected_route="south_west_gallery",
        memory_correct=(
            context["preferred_style"] == "classical"
            and context["wants_to_reach"] == "ancient_art_hall"
            and "avoid_crowd" not in context
        ),
    ))

    execute(
        reasoner, dispatcher,
        "Consigliami impressionismo evitando la folla",
        "s6_recommend", "session_crowd",
    )
    graph.update_room_state("impressionism_hall", crowd_level="high")
    decision, route, _ = execute(
        reasoner, dispatcher, "Portami lì", "s6_follow", "session_crowd"
    )
    results.append(result(
        "S6", "ambient_revalidation", decision, route,
        expected_status="no_match", expected_rejection="crowd_level_high",
    ))

    graph.update_room_state("impressionism_hall", crowd_level="low")
    decision, route, _ = execute(
        reasoner, dispatcher, "Portami lì", "s7_reset", "session_crowd"
    )
    results.append(result(
        "S7", "ambient_revalidation", decision, route,
        expected_status="success", expected_room="impressionism_hall",
        expected_route="north_gallery",
    ))

    execute(
        reasoner, dispatcher, "Consigliami qualcosa di classico evitando rumore",
        "s8_recommend", "session_noise",
    )
    graph.update_room_state("ancient_art_hall", noise_level="high")
    decision, route, _ = execute(
        reasoner, dispatcher, "Guide me there", "s8_follow", "session_noise"
    )
    results.append(result(
        "S8", "ambient_revalidation", decision, route,
        expected_status="no_match", expected_rejection="noise_level_high",
    ))
    return results


def metric(results, categories, field="decision_correct"):
    selected = [item for item in results if item["category"] in categories]
    return {
        "correct": sum(item[field] for item in selected),
        "total": len(selected),
        "accuracy": sum(item[field] for item in selected) / len(selected),
    }


def main():
    first = run_benchmark()
    second = run_benchmark()
    repeatable = first == second
    summary = {
        "benchmark": "bounded session-memory functional benchmark",
        "number_cases": len(first),
        "memory_write": metric(first, {"memory_write", "explicit_override"},
                               "memory_write_correct"),
        "follow_up_resolution": metric(
            first, {"follow_up", "explicit_override"}
        ),
        "session_isolation": metric(first, {"session_isolation"}),
        "explicit_override": metric(first, {"explicit_override"}),
        "ambient_revalidation": metric(first, {"ambient_revalidation"}),
        "route_policy": {
            "correct": sum(item["route_policy_correct"] for item in first),
            "total": len(first),
            "accuracy": sum(item["route_policy_correct"] for item in first)
            / len(first),
        },
        "deterministic_repeatability": repeatable,
    }
    print(json.dumps({"summary": summary, "cases": first}, indent=2))
    if not repeatable or not all(item["passed"] for item in first):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
