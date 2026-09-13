# Final Eight-Actor Social-Navigation Demo

This document describes the submitted animated social-navigation demonstration.

## Launch

From a desktop terminal in the repository root:

```bash
./scripts/stop_video1_animated_demo.sh 2>/dev/null || true
./scripts/start_video1_final_animated_demo.sh --actors 8 --runtime-audit
```

Stop with:

```bash
./scripts/stop_video1_animated_demo.sh
```

The launcher starts Gazebo, RViz, the runtime monitor, eight animated Actors, the `/people` bridge, Nav2, the custom social critic, the social-yield filter, and one navigation goal. Gazebo and RViz remain open after navigation completes until the stop helper is called.

## Final Demonstrated Configuration

The final scene contains eight walking Gazebo Actors. Their trajectories are deterministic and parameterized from fixed ellipses stored in `exchange/museum_ws/src/museum_video1_actors/config/eight_actors.json`.

Each Actor plugin controls only its own Actor model. TIAGo is never teleported and Actor code does not publish direct robot velocity commands.

The main robot target is:

```text
x = 0.0
y = 16.0
yaw = 1.5708
```

The launcher sends exactly one `NavigateToPose` action for this final social-navigation scene.

## Human-State Pipeline

Actor motion samples are aggregated and published as world-frame Actor state and as odom-frame `/people` messages. These messages provide the human positions and velocities used by the social-navigation layer.

The final navigation stack is:

```text
/people
   |
   +--> anisotropic ProxemicForceCritic
   |
Nav2 / DWB
   |
/cmd_vel_nav
   |
velocity smoother
   |
/museum/nav_cmd_vel
   |
social_yield
   |
/cmd_vel
   |
TIAGo base
```

The escorted visitor identifier remains excluded from the social critic where configured, while surrounding Actor identifiers are used for social avoidance/yielding.

## LiDAR and Actor Visibility

The museum LiDAR remains active and is used for museum geometry and Nav2 obstacle perception.

A controlled experiment with the exact `walk.dae` Actor asset, plugin, and GPU-LiDAR configuration showed no reliable Actor returns at TIAGo's approximately 0.195 m laser plane. Positive box controls were visible to the LiDAR, while the Actor was not.

Therefore the final animated demo intentionally uses `/people` for human-aware navigation rather than claiming that the Actor mesh is observed by the obstacle layer. This result applies only to this tested simulation configuration and should not be generalized to all human meshes, sensors, or heights.

## Anisotropic Proxemic Critic

The custom plugin is:

```text
museum_social_critic::ProxemicForceCritic
```

The accepted final configuration preserves the project social-navigation parameters, including:

```text
scale:                32
comfort distance:     1.0 m
sigma:                 0.4
front scale:           1.4
side scale:            1.0
back scale:            0.8
```

The critic predicts human position over the candidate trajectory horizon and evaluates directional proxemic distance. The social cost uses a logistic function of effective human-relative distance and aggregates the maximum cost over people and sampled trajectory points.

The directional geometry increases the effective comfort region in front of a moving person compared with the side/back region.

## Social Yield Layer

For visually clear crossing behavior, the demo also uses an explicit social-yield filter above the base velocity command.

It considers people in front of TIAGo and predicts entry into a forward corridor. Depending on geometry and time-to-crossing, the monitor may show:

```text
CLEAR
SLOW
YIELDING
RESUMING
```

The current configuration uses approximately:

```text
forward corridor half-width: 0.65 m
slowing distance:             2.5 m
stop distance:                1.6 m
prediction horizon:           2.0 s
release distance:             1.95 m
release half-width:           0.85 m
clear-time hysteresis:        0.8 s
input freshness bound:        0.4 s
```

The yield filter scales commanded translation and rotation together so commanded curvature is preserved. It does not cancel or reissue the final social-navigation goal.

## Runtime Monitor

The terminal monitor exposes compact evidence for the recording, including:

- navigation goal count;
- Actor count;
- `/people` stream status;
- CLEAR/SLOW/YIELDING/RESUMING social state;
- nearest relevant human;
- navigation status;
- recovery/controller error counters;
- robot motion evidence.

This makes it possible to show both the visible Gazebo behavior and the corresponding internal navigation state in the same video.

## Final Runtime Evidence

The progressive animated-Actor validation reached successful three-Actor and six-Actor stages before the final eight-Actor run.

The final eight-Actor GUI run completed with:

```text
Navigation:                    SUCCESS
NavigateToPose goals:          1
Slow/stop/resume evidence:     observed
Minimum human center distance: 0.782 m
Recoveries:                    0
Invalid trajectories:          0
Controller aborts:             0
Failed recoveries:             0
Acknowledgement timeouts:      0
Observed RTF:                  0.396
```

Two missed controller-loop warnings were recorded under load. The recorder's aggregate `people_fresh_and_frequent` flag was not satisfied for every observed sample in the eight-Actor run, so the documentation does not claim a perfect all-checks-pass aggregate. The visible run nevertheless reached the destination successfully and demonstrated the intended social slowdown/yield/resume behavior.

## Navigation Stability Notes

During system stabilization, a Humble Nav2 action acknowledgement deadline of 20 ms was reproduced as too short for this simulation load. The final launcher generates an effective per-run Nav2 YAML that changes only `default_server_timeout` to 200 ms while retaining the accepted controller and social-critic parameters.

The final configuration also keeps software rendering available for `gzserver` where required for valid GPU-LiDAR scans while allowing the GUI/RViz rendering path to use the desktop GPU.

These changes are runtime integration/stability measures; they do not change the social-critic cost function or semantic navigation target.

## Reproducibility

The final run is intended to be reproduced with:

```bash
./scripts/stop_video1_animated_demo.sh 2>/dev/null || true
./scripts/start_video1_final_animated_demo.sh --actors 8 --runtime-audit
```

No manual goal publication is required. All run-specific output is stored under the demo log directory generated by the launcher.
