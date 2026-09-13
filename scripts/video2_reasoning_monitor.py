#!/usr/bin/env python3
"""One real structured request; observe existing reasoning and route dispatch.

The Actor sample adapts the existing VisitorSession.observe mechanism. No
language model, synthetic graph facts, or navigation ActionClient is used.
"""
import argparse
import contextlib
import json
from pathlib import Path
import sys
import time
from types import SimpleNamespace

import rclpy
from ament_index_python.packages import get_package_share_directory
from rclpy.node import Node
from std_msgs.msg import String
from museum_assistant.visitor_session import VisitorSession
from museum_assistant.supplied_museum_navigation import load_route_plan

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'exchange/museum_ws/src/museum_video1_actors/scripts'))
from record_demo import Recorder

REQUEST_TEXT = 'I want to see classical art.'
REQUEST = dict(request_id='video2_request_1', intent='recommend_and_prepare_navigation',
               constraints={'style': 'classical'})


def presentation(request, decision, graph, route, config):
    """Validate cross-topic evidence and resolve physical coordinates from data."""
    if decision['request_id'] != request['request_id'] or decision['session_id'] != request['session_id']:
        raise ValueError('Decision correlation mismatch')
    if decision['status'] != 'success' or decision['skill'] != 'navigate_to':
        raise ValueError('Reasoner did not prepare navigation')
    if any(route[k] != decision[k] for k in ('request_id', 'session_id', 'selected_room')):
        raise ValueError('Route correlation mismatch')
    if route['route'] == 'north_gallery':
        raise ValueError('This demonstration requires a destination other than north_gallery')
    nodes = {n['id']: n for n in graph['nodes']}
    artworks = decision['matching_artworks']
    if not artworks:
        raise ValueError('Reasoner exposed no matching artwork')
    facts = []
    for artwork in artworks:
        node = nodes[artwork]
        if node['style'] != request['constraints']['style']:
            raise ValueError('Graph artwork does not match the request')
        edge = dict(source=artwork, relation='located_in', target=decision['selected_room'])
        if edge not in graph['edges']:
            raise ValueError('Selected artwork has no supporting located_in relation')
        facts += [f"{artwork} : style = {node['style']}",
                  f"{artwork} -> located_in -> {decision['selected_room']}"]
    plan = load_route_plan(route['route'], config/'supplied_museum_routes.yaml',
                           config/'supplied_museum_room_layout.yaml')
    goal = plan[-1]
    return dict(selected_entities=artworks, selected_room=decision['selected_room'],
                destination=route['route'], graph_facts=facts,
                goal=dict(x=goal.x, y=goal.y, yaw=goal.yaw),
                route_nodes=[p.name for p in plan], action=decision['skill'])


class Monitor(Node):
    def __init__(self, output):
        super().__init__('video2_reasoning_monitor')
        self.output = output
        self.events = (output/'reasoning_events.jsonl').open('w', buffering=1)
        self.received = {}
        self.counts = {}
        self.error = None
        self.request_count = 0
        self.request = None
        self.session = None
        self.config = Path(get_package_share_directory('museum_assistant'))/'config'
        self.publisher = self.create_publisher(String, '/museum/user_request', 10)
        self.session_publisher = self.create_publisher(String, '/museum/session_state', 10)
        for topic in ('assistant_response', 'scene_graph', 'supplied_route_request', 'session_state', 'user_request'):
            self.create_subscription(String, '/museum/'+topic,
                                     lambda msg, key=topic: self.receive(key, msg), 10)

    def receive(self, key, msg):
        try:
            value = json.loads(msg.data)
            self.events.write(json.dumps(dict(topic='/museum/'+key, value=value))+'\n')
            self.received[key] = value
            self.counts[key] = self.counts.get(key, 0)+1
            if key in ('user_request', 'supplied_route_request') and self.counts[key] > 1:
                raise ValueError(f'More than one {key} observed')
        except Exception as exc:
            self.error = f'{key}: {exc}'

    def run(self):
        # Reuse the proven readiness checks ONLY; Recorder.run() is never called.
        args = SimpleNamespace(output=str(self.output), mode='actor', actor_count=1,
                               goal_time=60., observe_only=True, runtime_audit=False)
        gate = Recorder(args)
        try:
            deadline = time.monotonic()+600
            with (self.output/'readiness.log').open('w') as log, contextlib.redirect_stdout(log):
                while not gate.ready():
                    gate.step()
                    if time.monotonic() > deadline:
                        raise TimeoutError('Simulation readiness deadline exceeded')
            people = gate.people[-1].pedestrians
            if len(people) != 1 or people[0].identifier != 'walker_1':
                raise ValueError('Expected exactly one observed Actor')
            # Identity adapter: the physics-backed walker_1 is the sole visitor.
            self.session = VisitorSession('walker_1').observe([p.identifier for p in people]).to_dict()
            readiness = dict(actor_count=1, actor_id=people[0].identifier,
                             nav2_active=gate.nav_active(), lidar=gate.scan_health,
                             simulation_time=gate.now())
        finally:
            gate.events.close()
            gate.action.destroy()
            gate.destroy_node()
        deadline = time.monotonic()+30
        while (self.publisher.get_subscription_count() < 2 or
               self.count_subscribers('/museum/assistant_response') < 2):
            rclpy.spin_once(self, timeout_sec=.05)
            if time.monotonic() > deadline:
                raise TimeoutError('Reasoner/dispatcher interfaces not ready')
        self.session_publisher.publish(String(data=json.dumps(self.session)))
        self.request = dict(REQUEST, session_id=self.session['session_id'])
        self.publisher.publish(String(data=json.dumps(self.request)))
        self.request_count += 1
        print(f'Visitor: {self.session["track_id"]} | Structured request: "{REQUEST_TEXT}"\nWaiting for the real reasoner...', flush=True)
        deadline = time.monotonic()+30
        required = {'assistant_response', 'scene_graph', 'supplied_route_request', 'session_state', 'user_request'}
        while not required.issubset(self.received):
            rclpy.spin_once(self, timeout_sec=.05)
            if self.error:
                raise RuntimeError(self.error)
            if time.monotonic() > deadline:
                raise TimeoutError('Missing runtime evidence: '+str(required-self.received.keys()))
        result = presentation(self.request, self.received['assistant_response'],
                              self.received['scene_graph'], self.received['supplied_route_request'], self.config)
        # Briefly drain duplicate requests/dispatches before declaring success.
        deadline = time.monotonic()+2
        while time.monotonic() < deadline:
            rclpy.spin_once(self, timeout_sec=.05)
        if self.error:
            raise RuntimeError(self.error)
        summary = dict(status='SUCCESS', request_text=REQUEST_TEXT, input_mode='structured_json',
                       request=self.request, request_count_sent=self.request_count,
                       observed_counts=self.counts, session=self.received['session_state'],
                       readiness=readiness, navigation_started=False, **result)
        (self.output/'reasoning_summary.json').write_text(json.dumps(summary, indent=2)+'\n')
        print('\n'+'='*62+'\n             SEMANTIC MUSEUM REASONING DEMO\n'+'='*62)
        print(f"Visitor: {self.session['track_id']}   Session: {self.session['state']}")
        print(f'\nUSER REQUEST (deterministic structured input)\n  "{REQUEST_TEXT}"')
        print(f"\nUNDERSTANDING\n  Intent: {self.request['intent']}\n  Style: {self.request['constraints']['style']}")
        print('\nSCENE GRAPH\n  '+'\n  '.join(result['graph_facts']))
        print(f"\nREASONING\n  Matching entities: {', '.join(result['selected_entities'])}\n  Selected room: {result['selected_room']}")
        print(f"\nPHYSICAL ROUTE MAPPING (existing configuration)\n  {result['selected_room']} -> {result['destination']}")
        print(f"\nROBOT ACTION\n  {result['action']} — PREPARED, not sent to Nav2\n  Target: {result['destination']}\n  Final goal: {result['goal']}")
        print('\nSTATUS: SUCCESS (reasoning and route preparation)\n'+'='*62, flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    rclpy.init()
    node = Monitor(args.output)
    try:
        node.run()
    except Exception as exc:
        (args.output/'reasoning_summary.json').write_text(json.dumps(dict(status='ERROR', error=str(exc), request_count_sent=node.request_count), indent=2))
        print(f'Reasoning demo failed: {exc}', flush=True)
        raise
    finally:
        node.events.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
