#!/usr/bin/env python3
"""Run the three required reasoning-to-route decisions without ROS or Gazebo."""

import json
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = REPO_ROOT / "exchange/museum_ws/src/museum_assistant"
sys.path.insert(0, str(PACKAGE_ROOT))

from museum_assistant.reasoning import DeterministicReasoner  # noqa: E402
from museum_assistant.semantic_graph import load_semantic_graph  # noqa: E402
from museum_assistant.semantic_route_dispatch import (  # noqa: E402
    ReasoningRouteDispatcher,
    SemanticRouteResolver,
)


CONFIG = PACKAGE_ROOT / "config"
CASES = (
    ("offline_impressionism", {"style": "impressionism"}),
    ("offline_classical", {"style": "classical"}),
    ("offline_children", {"child_friendly": True}),
)


def main() -> None:
    graph = load_semantic_graph(CONFIG / "semantic_map.yaml")
    reasoner = DeterministicReasoner(graph)
    resolver = SemanticRouteResolver.from_files(
        CONFIG / "supplied_museum_semantic_routes.yaml",
        graph,
        CONFIG / "supplied_museum_routes.yaml",
        CONFIG / "supplied_museum_room_layout.yaml",
    )
    dispatcher = ReasoningRouteDispatcher(resolver)
    results = []
    for request_id, constraints in CASES:
        request = {
            "request_id": request_id,
            "session_id": "offline_session",
            "intent": "recommend_and_prepare_navigation",
            "constraints": constraints,
        }
        decision = reasoner.handle_request(request)
        dispatch = dispatcher.prepare(decision)
        if not dispatch.dispatched:
            raise RuntimeError(
                f"Offline decision {request_id} was not dispatched: "
                f"{dispatch.reason}"
            )
        results.append(
            {
                "request": request,
                "decision": decision,
                "route_request": dispatch.route_request,
            }
        )
    print(json.dumps(results, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
