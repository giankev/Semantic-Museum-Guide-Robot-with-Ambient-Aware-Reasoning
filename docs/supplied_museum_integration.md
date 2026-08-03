# Supplied Museum Integration

## Status

The supplied environment is a **PARTIAL** integration. Its assets are portable,
installed by `museum_assistant`, and runtime-validated with TIAGo in Gazebo.
An occupancy map suitable for the robot footprint and inflation radius could
not be produced reliably from the available wheel odometry and repetitive
gallery geometry. No supplied-museum map, AMCL/Nav2 launch, semantic-pose
variant, or default-environment switch is therefore accepted or committed.

Phase 8 speech-to-text was not run or modified during this work. The complete
package test command necessarily collected its existing unit tests, but no
audio, Whisper, cloud API, or API key was used.

## Supplied Assets And Portable Packaging

The original `museum_env/` tree contained 40 files and 30,859,585 bytes:

- one SDF 1.6 world, `museum.world`;
- one COLLADA 1.4.1 visual mesh, `model.dae`;
- 30 PNG and 8 JPG texture files.

The original DAE uses metres, `Y_UP`, and references 29 images. All 29
references resolve, and the other nine images are preserved as supplied
alternates. The original DAE and every image are unedited. Its SHA-256 is
`1cbf192617b42eb934c1edd62a9ed307fa33c482022d375f4d35141b1caa3210`.

The tree now has one installed source of truth at:

```text
exchange/museum_ws/src/museum_assistant/worlds/supplied_museum/
```

The world uses `model.dae` and `collision.dae` relative to its own installed
location. This replaces the supplied machine-specific
`file:///Desktop/museum_env/model.dae` URI without introducing a host or
container absolute path. `setup.py` installs the world, both DAE files, and
all textures. Source and installed-share inventories were compared after the
build and were identical and non-empty.

The visual mesh is approximately 122 m by 47 m and 6 m high after its world
rotation. The original scene had one sun light, no Gazebo plugin, and a large
box floor. Integration adds the existing project-compatible
`gazebo_ros_state` plugin and the three visual-only human markers at verified
open locations:

| Gazebo model | World pose `(x, y, z)` | Public ID used by existing adapters |
| --- | --- | --- |
| `visitor_marker` | `(-1.0, 0.0, 0.0)` | `visitor_1` |
| `guide_marker` | `(1.2, 9.0, 0.0)` | `guide_1` |
| `staff_marker` | `(35.0, 0.0, 0.0)` | `staff_1` |

The dedicated launch resolves the installed package share and reuses the
public TIAGo Gazebo launch:

```bash
ros2 launch museum_assistant tiago_supplied_museum_world.launch.py gzclient:=false
```

It intentionally does not start SLAM, Nav2, reasoning, escort, people, or
social navigation. The previously validated `tiago_museum_world.launch.py`,
world, map, and navigation launches remain available and unchanged.

## Collision Findings And Minimal Repair

The supplied `model.dae` was tested as both visual and collision geometry
before modification. It reproduced two concrete physical defects:

1. A visually disconnected, full-height one-metre box at world
   `x=20.20..21.20`, `y=0..1`, `z=0..5` blocked the east corridor. TIAGo
   reached about `x=20.03`, then was physically ejected backward; the result
   repeated twice.
2. The large triangulated mesh floor gave the mobile base poor wheel contact.
   A closed-loop turn measured about 1.54 times more wheel-odometry rotation
   than Gazebo rotation.

`collision.dae` is a mechanical derivative of the unmodified visual DAE. It
removes only the 12 triangles of the reproduced blocking box and the 416
triangles of the connected imported floor component. The affected COLLADA
polygon count changes from 7,012 to 6,584; source arrays, materials, remaining
polygon order, ceiling, walls, exhibits, and visual geometry are preserved.
Focused tests pin the exact removed indices and the floor-component hash so
the repair cannot silently widen.

The original world box is retained as the physical floor, moved to its visible
surface at `z=-0.011`, and assigned ODE friction `mu=10`, `mu2=10`. With this
repair, a slow probe crossed the former obstruction from `x=18` to `x=22.973`
at `y=-0.036` without an impulse; repeated faster passes reached about `x=28`.
The north route was also driven beyond its portal to approximately `y=17`.
A straight-motion diagnostic measured 5.021 m in Gazebo versus 5.074 m in
odometry, although longer routes with turns still accumulated unacceptable
heading error.

## Gazebo Runtime Evidence

The installed world passed `gz sdf -k`. The dedicated headless launch exposed
`floor`, `museum`, all three human markers, and `tiago` in roughly six seconds.
There were no missing DAE, texture, or `MeshShape` errors. TIAGo remained
stable near its configured spawn `(0, 0, 0)`, with observed vertical pose near
`z=-0.001`, and did not intersect the floor or museum at rest.

The run provided active `/clock`, `/joint_states`, `/scan_raw`,
`/ground_truth_odom`, `/mobile_base_controller/odom`, and the expected robot TF
frames. Physical teleoperation/probe motion crossed both the north doorway and
the repaired east corridor. Software-rendered default physics achieved an
approximate real-time factor of 0.18 on the target machine. This is usable for
validation but slow; visual rendering alone was not treated as collision
evidence.

## Occupancy Mapping Attempts And Blocker

No pre-existing occupancy map was aligned to this supplied world. Five maps
were generated from the real `/scan_raw` stream and physical robot motion;
each was rejected rather than manually edited into apparent alignment:

| Attempt | Map image | Resolution/origin | Rejection evidence |
| --- | --- | --- | --- |
| Original mesh floor, wheel odometry | 1200 x 834 | 0.05 m, `(-12.2, -8.43)` | Final Gazebo pose about `(33.82, -0.02, 0.08)` disagreed with odometry `(-28.86, 22.15, -2.58)`; map was corrupt. |
| Box floor, wheel odometry | 1020 x 625 | 0.05 m, `(-11.4, -9.18)` | Rigid calibration left about 0.11 m passage clearance and ghost walls. |
| Open-loop wheel controller experiment | 1032 x 617 | 0.05 m, `(-12.0, -8.76)` | About 0.11 m passage clearance and ghost walls remained. |
| Ground-truth mapping TF, scan matching | 1111 x 1103 | 0.05 m, `(-18.4, -32.9)` | Repetitive galleries produced false associations; the north route remained unknown. |
| Ground-truth mapping TF, matching/loop closure disabled | 758 x 1089 | 0.05 m, `(-18.2, -8.42)` | North centerline contained occupied cells and the repaired passage provided only about 0.472 m clearance. |

The accepted robot radius plus configured inflation requires approximately
0.68 m (`0.28 + 0.40`). The last map therefore could not support honest Nav2
acceptance even after simultaneous final-pose calibration. All generated map
files were removed from the repository. The committed legacy map still belongs
only to the original lightweight world.

Because this gate failed, the following supplied-world values do not exist and
must not be inferred from legacy evidence:

- accepted map YAML/image, source, origin, or final resolution;
- AMCL initial pose, settled estimate, or localization error;
- supplied-world manual `NavigateToPose` results;
- calibrated semantic room `nav_pose` values;
- semantic navigation, visitor/session, escort, or `/people` runtime results;
- ProxemicForceCritic load or baseline/social comparison;
- the Phase 7 text-to-navigation integrated result.

The physical areas inspected as likely future calibration candidates are the
central `main_corridor`, the north gallery route, and the east gallery beyond
the repaired opening. They are not assigned semantic room IDs until an aligned
map makes their navigation poses testable.

## Build And Automated Tests

Inside `museum-tiago:humble`:

```bash
colcon build --symlink-install \
  --packages-select museum_assistant museum_social_critic
colcon test --packages-select museum_assistant museum_social_critic
colcon test-result --verbose
```

Both packages built successfully. `museum_assistant` passed 98 collected
tests and `museum_social_critic` passed six C++ tests. The aggregate result was
105 tests, zero errors, zero failures, and zero skipped. The aggregate includes
one package-level result in addition to the directly collected cases. Five new
tests cover portable SDF paths, DAE texture resolution, the bounded collision
derivative, installed asset parity, and installed launch-path resolution.

No protected reasoning, language, navigation, escort, people, social-critic,
or Phase 8 source was changed.

## Failed And Reverted Experiments

- The original collision mesh was retained until the east blockage and floor
  contact defects were reproduced. Only their evidenced components were then
  removed from the collision derivative.
- Applying friction to the entire mesh improved the turn ratio only from about
  1.54 to 1.35 and was reverted; using the box floor produced about 1.19.
- Physics steps of `0.01/100` and `0.005/200` prevented useful translation.
  A `0.002/500` experiment ran faster but made the collision event unstable.
  All were reverted to the supplied/default physics settings.
- An open-loop base-controller experiment was symmetric for a small turn but
  still accumulated large error on a mapping route. It was not integrated.
- Mapping-only ground-truth TF experiments were temporary and removed. They
  did not change runtime robot localization or the project TF contract.
- All five invalid maps and task-created temporary mapping logs were removed;
  no generated map or runtime artifact is committed.

## Remaining Work

The supplied variant should remain opt-in. A future bounded task must first
produce and independently validate an aligned occupancy map from a reliable
pose source. Only then should it add supplied-world AMCL/Nav2 launch data,
calibrate the three semantic poses, and run the downstream acceptance matrix.
The documented default must not change before those checks pass.
