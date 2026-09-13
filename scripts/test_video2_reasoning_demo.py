"""Real project contracts, graph and resolver: no Gazebo required."""
from copy import deepcopy
import json
from pathlib import Path
import unittest

from museum_assistant.reasoning import DeterministicReasoner
from museum_assistant.semantic_graph import load_semantic_graph
from museum_assistant.semantic_route_dispatch import SemanticRouteResolver, ReasoningRouteDispatcher
from museum_assistant.visitor_session import VisitorSession
from video2_reasoning_monitor import REQUEST, presentation

CONFIG = Path(__file__).resolve().parents[1]/'exchange/museum_ws/src/museum_assistant/config'


class ReasoningDemoTests(unittest.TestCase):
    def evidence(self, style='classical'):
        graph = load_semantic_graph(CONFIG/'semantic_map.yaml')
        session = VisitorSession('walker_1').observe(['walker_1'])
        request = dict(REQUEST, constraints={'style': style}, session_id=session.session_id)
        decision = DeterministicReasoner(graph).handle_request(request)
        resolver = SemanticRouteResolver.from_files(CONFIG/'supplied_museum_semantic_routes.yaml', graph,
            CONFIG/'supplied_museum_routes.yaml', CONFIG/'supplied_museum_room_layout.yaml')
        route, _ = ReasoningRouteDispatcher(resolver).prepare(decision)
        return request, decision, graph.snapshot(), route

    def test_existing_classical_entity_resolves_to_south_west(self):
        result = presentation(*self.evidence(), CONFIG)
        self.assertEqual(result['selected_entities'], ['roman_statue'])
        self.assertEqual(result['selected_room'], 'ancient_art_hall')
        self.assertEqual(result['destination'], 'south_west_gallery')
        self.assertEqual(result['goal'], dict(x=-10., y=-21.5, yaw=1.5708))

    def test_different_semantic_requirement_changes_entity_and_destination(self):
        result = presentation(*self.evidence('interactive'), CONFIG)
        self.assertEqual(result['selected_entities'], ['interactive_light_installation'])
        self.assertEqual(result['destination'], 'south_east_gallery')
        self.assertEqual(result['goal']['x'], 10.)

    def test_north_gallery_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'north_gallery'):
            presentation(*self.evidence('impressionism'), CONFIG)

    def test_missing_graph_relation_cannot_be_presented_as_fact(self):
        request, decision, graph, route = self.evidence()
        graph['edges'] = []
        with self.assertRaisesRegex(ValueError, 'located_in'):
            presentation(request, decision, graph, route, CONFIG)

    def test_mismatched_route_is_rejected(self):
        request, decision, graph, route = self.evidence()
        route['request_id'] = 'unrelated'
        with self.assertRaisesRegex(ValueError, 'correlation'):
            presentation(request, decision, graph, route, CONFIG)

    def test_session_requires_observed_actor(self):
        session = VisitorSession('walker_1')
        self.assertIsNone(session.observe([]))
        self.assertEqual(session.observe(['walker_1']).track_id, 'visitor_1')


if __name__ == '__main__':
    unittest.main()
