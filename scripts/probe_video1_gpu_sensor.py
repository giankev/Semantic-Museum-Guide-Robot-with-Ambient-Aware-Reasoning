#!/usr/bin/env python3
"""Independent CPU/GPU laser positive control inside the existing Docker image.

Uses its own Gazebo master and ROS domain. No TIAGo model or navigation action.
Keep the Ogre log with the JSON to identify the actual renderer.
"""
import argparse
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import time


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    os.environ['GAZEBO_MASTER_URI'] = 'http://127.0.0.1:11347'
    os.environ['ROS_DOMAIN_ID'] = '179'
    os.environ['GAZEBO_LOG_PATH'] = str(output)
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import LaserScan
    sensors = []
    for kind in ('ray', 'gpu_ray'):
        sensors.append(f'''<sensor name="{kind}" type="{kind}"><always_on>true</always_on>
        <update_rate>10</update_rate><ray><scan><horizontal><samples>100</samples>
        <min_angle>-0.5</min_angle><max_angle>0.5</max_angle></horizontal></scan>
        <range><min>0.05</min><max>10</max><resolution>0.01</resolution></range></ray>
        <plugin name="{kind}_ros" filename="libgazebo_ros_ray_sensor.so"><ros>
        <remapping>~/out:=/audit/{kind}</remapping></ros>
        <output_type>sensor_msgs/LaserScan</output_type><frame_name>audit_laser</frame_name></plugin></sensor>''')
    world = output/'sensor.world'
    world.write_text('''<sdf version="1.6"><world name="audit_sensor">
    <physics type="ode"><max_step_size>0.001</max_step_size><real_time_update_rate>1000</real_time_update_rate></physics>
    <model name="target"><static>true</static><pose>2 0 0.5 0 0 0</pose><link name="box">
    <collision name="box"><geometry><box><size>0.4 2 1</size></box></geometry></collision>
    <visual name="box"><geometry><box><size>0.4 2 1</size></box></geometry></visual></link></model>
    <model name="sensor"><static>true</static><pose>0 0 0.5 0 0 0</pose><link name="laser">'''
    + ''.join(sensors) + '</link></model></world></sdf>')
    samples = {kind: [] for kind in ('ray', 'gpu_ray')}
    rclpy.init()
    node = Node('video1_sensor_control')
    for kind in samples:
        def receive(msg, key=kind):
            values = list(msg.ranges)
            finite = [v for v in values if math.isfinite(v)]
            samples[key].append(dict(total=len(values), finite=len(finite), angle_min=msg.angle_min, angle_max=msg.angle_max,
                minimum=min(finite) if finite else None,
                negative_inf=sum(v == -math.inf for v in values),
                positive_inf=sum(v == math.inf for v in values)))
        node.create_subscription(LaserScan, '/audit/'+kind, receive, qos_profile_sensor_data)
    with (output/'server.log').open('w') as log:
        process = subprocess.Popen(['gzserver', '--verbose', '-s', 'libgazebo_ros_init.so',
                                    '-s', 'libgazebo_ros_factory.so', str(world)],
                                   stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            deadline = time.monotonic()+40
            while time.monotonic() < deadline and process.poll() is None:
                rclpy.spin_once(node, timeout_sec=.1)
                if all(len(v) >= 20 for v in samples.values()):
                    break
        finally:
            os.killpg(process.pid, signal.SIGINT) if process.poll() is None else None
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            node.destroy_node()
            rclpy.shutdown()
    passed = all(len(v) >= 20 and all(s['finite'] == 100 and
                 abs(s['minimum']-1.8) < .02 for s in v) for v in samples.values())
    report = dict(passed=passed, expected_minimum=1.8, samples=samples,
                  environment={k: os.environ.get(k) for k in ('__NV_PRIME_RENDER_OFFLOAD',
                      '__GLX_VENDOR_LIBRARY_NAME', 'LIBGL_ALWAYS_SOFTWARE', 'GAZEBO_MASTER_URI', 'ROS_DOMAIN_ID')})
    (output/'summary.json').write_text(json.dumps(report, indent=2)+'\n')
    print(json.dumps(report))
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
