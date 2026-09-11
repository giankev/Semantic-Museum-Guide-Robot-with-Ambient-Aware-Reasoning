#!/usr/bin/env python3
"""Read-only, bounded-rate TF/plan/scan evidence for navigation diagnosis.

No goals, controller changes or entity-state writes. Can also inspect a running
POC independently: python3 runtime_audit.py --output DIR --seconds 15.
"""
import argparse
import json
import math
from pathlib import Path
import time

import rclpy
from geometry_msgs.msg import PoseWithCovarianceStamped
from nav_msgs.msg import OccupancyGrid, Odometry, Path as NavPath
from rcl_interfaces.msg import Log
from rclpy.node import Node
from rclpy.parameter import Parameter
from rclpy.qos import qos_profile_sensor_data, QoSProfile, DurabilityPolicy
from rclpy.time import Time
from sensor_msgs.msg import LaserScan
from tf2_ros import Buffer, TransformListener
from demo_math import stamp_seconds, yaw


def pose(p):
    return [p.position.x, p.position.y, yaw(p.orientation)]


def cell_at(grid, x, y):
    """OccupancyGrid origin is a pose, not necessarily an axis-aligned offset."""
    origin = grid.info.origin
    angle = yaw(origin.orientation)
    dx, dy = x - origin.position.x, y - origin.position.y
    c, s = math.cos(angle), math.sin(angle)
    col = math.floor((c * dx + s * dy) / grid.info.resolution)
    row = math.floor((-s * dx + c * dy) / grid.info.resolution)
    if 0 <= col < grid.info.width and 0 <= row < grid.info.height:
        return int(grid.data[row * grid.info.width + col])
    return None


class RuntimeAudit:
    def __init__(self, node, output):
        self.node = node
        self.output = Path(output)
        self.output.mkdir(parents=True, exist_ok=True)
        self.file = (self.output / 'runtime_audit.jsonl').open('w', buffering=1)
        self.tf = getattr(node, 'tf', None)
        self.listener = None
        if self.tf is None:
            self.tf = Buffer()
            self.listener = TransformListener(self.tf, node)
        self.latest = {}
        self.last_snapshot = 0.0
        self.map_saved = False
        for kind, topic in ((Odometry, '/ground_truth_odom'),
                            (Odometry, '/museum/ground_truth_odom'),
                            (Odometry, '/mobile_base_controller/odom'),
                            (PoseWithCovarianceStamped, '/amcl_pose'),
                            (NavPath, '/plan'), (NavPath, '/local_plan'),
                            (NavPath, '/received_global_plan'), (NavPath, '/transformed_global_plan'),
                            (OccupancyGrid, '/local_costmap/costmap'),
                            (OccupancyGrid, '/global_costmap/costmap'),
                            (LaserScan, '/scan_raw')):
            node.create_subscription(kind, topic,
                                     lambda m, t=topic: self.latest.update({t: m}),
                                     qos_profile_sensor_data)
        node.create_subscription(OccupancyGrid, '/map', self.save_map,
                                 QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))
        # Publisher attribution uses tf_authority_audit (rclcpp MessageInfo),
        # because early Humble rclpy discards the publisher GID.
        callback = (node.guard('runtime_audit/rosout', self.on_log)
                    if hasattr(node, 'guard') else self.on_log)
        node.create_subscription(Log, '/rosout', callback, qos_profile_sensor_data)
        # Wall-time throttling is checked by tick, including when /clock pauses.

    def write(self, kind, **data):
        self.file.write(json.dumps(dict(kind=kind, wall=time.time(),
                        sim=self.node.get_clock().now().nanoseconds / 1e9, **data),
                        allow_nan=False) + '\n')

    def save_map(self, msg):
        if self.map_saved:
            return
        try:
            import gzip
            with gzip.open(self.output / 'audit_map.json.gz', 'wt') as f:
                json.dump(dict(frame=msg.header.frame_id, origin=pose(msg.info.origin),
                               width=msg.info.width, height=msg.info.height,
                               resolution=msg.info.resolution, data=list(msg.data)), f)
            self.map_saved = True
        except Exception as exc:
            self.write('diagnostic_error', source='save_map', error=str(exc))

    def on_log(self, msg):
        if any(s in msg.msg for s in ('No valid trajectories', 'Critic', 'zero length',
                                     'acknowledge goal', 'Aborting handle', 'time allowance')):
            self.write('navigation_event', node=msg.name, text=msg.msg,
                       log_stamp=stamp_seconds(msg.stamp))
            self.tick(force=True)

    def lookup(self, target, source):
        t = self.tf.lookup_transform(target, source, Time())
        p, q = t.transform.translation, t.transform.rotation
        return dict(pose=[p.x, p.y, yaw(q)], stamp=stamp_seconds(t.header.stamp))

    def tick(self, force=False):
        now = time.monotonic()
        if now - self.last_snapshot < (0.1 if force else 1.0):
            return
        self.last_snapshot = now
        try:
            self.snapshot()
        except Exception as exc:
            self.write('diagnostic_error', source='snapshot', error=str(exc))

    def snapshot(self):
        row = dict(transforms={}, odometry={}, plans={}, costmaps={})
        for target, source in (('map', 'odom'), ('odom', 'base_footprint'),
                               ('map', 'base_footprint'), ('base_footprint', 'base_laser_link')):
            try:
                row['transforms'][target + '<-' + source] = self.lookup(target, source)
            except Exception as exc:
                row['transforms'][target + '<-' + source] = dict(error=str(exc))
        for topic, m in self.latest.items():
            if isinstance(m, (Odometry, PoseWithCovarianceStamped)):
                row['odometry'][topic] = dict(frame=m.header.frame_id,
                    stamp=stamp_seconds(m.header.stamp), pose=pose(m.pose.pose),
                    covariance=list(m.pose.covariance))
            elif isinstance(m, NavPath):
                row['plans'][topic] = dict(frame=m.header.frame_id,
                    stamp=stamp_seconds(m.header.stamp), points=[pose(p.pose) for p in m.poses])
            elif isinstance(m, OccupancyGrid):
                row['costmaps'][topic] = dict(frame=m.header.frame_id,
                    stamp=stamp_seconds(m.header.stamp), origin=pose(m.info.origin),
                    width=m.info.width, height=m.info.height, resolution=m.info.resolution)
        grid, plan = self.latest.get('/local_costmap/costmap'), self.latest.get('/plan')
        if grid is not None and plan is not None:
            try:
                tx, ty, a = self.lookup(grid.header.frame_id, plan.header.frame_id)['pose']
                c, s = math.cos(a), math.sin(a)
                cells = [cell_at(grid, tx + c*p.pose.position.x - s*p.pose.position.y,
                                 ty + s*p.pose.position.x + c*p.pose.position.y) for p in plan.poses]
                row['plan_in_local_costmap'] = dict(cells=cells, total=len(cells),
                    inside=sum(v is not None for v in cells), free=sum(v == 0 for v in cells),
                    lethal=sum(v == 100 for v in cells), transform_policy='latest')
            except Exception as exc:
                row['plan_in_local_costmap'] = dict(error=str(exc))
        scan = self.latest.get('/scan_raw')
        if scan is not None:
            row['scan'] = dict(frame=scan.header.frame_id, stamp=stamp_seconds(scan.header.stamp),
                angle_min=scan.angle_min, angle_increment=scan.angle_increment,
                range_min=scan.range_min, range_max=scan.range_max,
                finite_returns=sum(math.isfinite(x) for x in scan.ranges),
                negative_inf=sum(x == -math.inf for x in scan.ranges),
                positive_inf=sum(x == math.inf for x in scan.ranges),
                nan_returns=sum(math.isnan(x) for x in scan.ranges),
                ranges=[round(x, 4) if math.isfinite(x) else None for x in scan.ranges])
            try:
                row['transforms']['base_footprint<-' + scan.header.frame_id] = self.lookup('base_footprint', scan.header.frame_id)
            except Exception as exc:
                row['scan']['transform_error'] = str(exc)
        self.write('snapshot', **row)

    def close(self):
        publishers = {}
        for topic in ('/tf', '/tf_static', '/ground_truth_odom', '/museum/ground_truth_odom',
                      '/mobile_base_controller/odom', '/people'):
            publishers[topic] = [dict(node=i.node_namespace.rstrip('/') + '/' + i.node_name,
                                    gid=bytes(i.endpoint_gid).hex())
                                 for i in self.node.get_publishers_info_by_topic(topic)]
        self.write('tf_authorities', tree=self.tf.all_frames_as_yaml(), publishers=publishers,
                   authority_status='USE_TF_AUTHORITY_AUDIT_FOR_PER_EDGE_GIDS')
        self.file.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    parser.add_argument('--seconds', type=float, default=15)
    args = parser.parse_args()
    rclpy.init()
    node = Node('video1_runtime_audit', parameter_overrides=[Parameter('use_sim_time', value=True)])
    audit = RuntimeAudit(node, args.output)
    end = time.monotonic() + args.seconds
    try:
        while rclpy.ok() and time.monotonic() < end:
            rclpy.spin_once(node, timeout_sec=0.05)
            audit.tick()
    finally:
        audit.close()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()
