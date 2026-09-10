# One-Actor real-machine acceptance audit

Run: `log/video1_animated/20260910T215802Z_actor/`.
Tested commit: `2e7fc400e4ac8203503295755543e43f04b92c5a`.
Audit date: 2026-09-11. Source working-tree status recorded by the run: clean.

**Result: successful navigation and working Actor/DDS/GUI pipeline, but the
requested gate for crowd expansion does not pass.** Condition 10 fails.
Do not relabel this run as a clean final-video acceptance or expand the crowd
on the basis of the eventual NavigateToPose SUCCESS alone.

| Requested check | Result | Evidence |
| --- | --- | --- |
| DDS admission | PASS | Separate process PID 1592, domain 107; participant creation, clock, map, people and controller-manager response all passed. |
| Nav2 ACTIVE | PASS | Both lifecycle managers report managed nodes active; recorder readiness at sim 10.85 s. |
| Exactly one goal | PASS | One `goal_sent` event; one observed goal UUID `63db5eaebb4e4f05b60a0c90609eca5b`. |
| Goal `(0,16,1.5708)` | PASS | Event records x=0.0, y=16.0, yaw=1.5708 at sim 60.0 s, in map frame per recorder source. |
| `walker_1` on `/people` | PASS | 4,824 recorded messages; unique walker identifier. |
| Meaningful velocity | PASS | Min/mean/max 0.126/0.26115/0.364 m/s; 100% above 0.10 m/s, no zero samples. |
| Actor pose validation | PASS | 576 observations; maximum error 0.00072784 m. |
| ProxemicForce scoring | PASS | 3,555 evaluations with critic scores, 849 nonzero and 1,017 varied-score samples; accepted parameters match. |
| Navigation completion | PASS | Nav2 reports goal succeeded; summary SUCCESS at sim 265.42 s. |
| No pathological recovery/trajectory failures | FAIL | 11 recovery count reported via Nav2 feedback, 17 no-valid-trajectory warnings, failed spin and backup recovery actions. No failed-to-make-progress messages. |

## Navigation failures are not startup-only artifacts

The full 44,606-line runtime log includes these specific events (line numbers
refer to the original run file, which remains unchanged):

- Lines 44228–44235: `follow_path` goal acknowledgement timeouts, a local
  costmap clear, an aborted controller action, a missed 8 Hz control loop,
  and entry into spin recovery.
- Lines 44242–44244: spin exceeded its time allowance and failed.
- Lines 44365 onward: `GoalDistCritic` found no global-plan points in the local
  costmap; `PathDistCritic` found no suitable free plan points there. Seventeen
  no-valid-trajectory warnings followed. Adjacent recorder observations place
  those warnings at approximately sim 240.9–241.85 s, well after the goal.
- Lines 44525–44529: resulting plan had zero poses, controller patience was
  exceeded, and the controller action aborted.
- Lines 44530–44536: backup ran and then failed its time allowance.
- Lines 44571–44572: the robot eventually reached the goal and Nav2 succeeded.

These are observed controller/action/plan problems. Their underlying cause is
not established by this recording. In particular, the evidence does not prove
that ProxemicForce tuning or human LiDAR collisions caused them. Do not change
accepted parameters, the critic, or human trajectories based on that inference.
The next investigation should correlate plan/costmap/TF geometry and action
acknowledgement timing at those events, retaining the same one-Actor setup.

## Startup and navigation measurements must be distinguished

The summary's maximum people gap of 16.3 simulation seconds occurred between
sim 15.4 and 31.7, **before** goal submission at sim 60.0. Recomputing only the
navigation interval from the original observations gives:

- 4,109 people samples, sim 60.0 through 265.4;
- 20.0 Hz in simulation time;
- maximum interval 0.05 simulation seconds;
- speed range 0.126–0.364 m/s.

Thus the whole-run freshness check fails, but this is not evidence of a
people-stream outage during navigation. The summary also retains startup
parameter/service diagnostics and marks instrumentation incomplete. Those
issues should not erase the demonstrated navigation success, nor should they
be confused with the genuine recovery and trajectory failures above.

Additional measurements:

- Minimum human-center separation: 1.02753 m; estimated disk clearance:
  0.39753 m, not a mesh-contact measurement.
- Maximum stationary spin: 3.84 simulation seconds; angular reversals: 7.
- Final map pose: `(-0.17976, 15.96828, 1.22278)`; positional goal check passed.
- Final world pose: `(1.29865, 15.63557, 1.07119)`; the recorder's separate
  physical-position check failed. The map/world discrepancy needs investigation;
  the submitted navigation goal was nevertheless the exact requested map goal.
- RTF measured by recorder: 0.43628. GUI FPS: approximately 40, **reported by
  the user**, not instrumented (`gazebo_gui_fps` is null).
- Gazebo and RViz visible, TIAGo visible, Actor visible and moving: confirmed
  by the user's real-machine observations.

## LiDAR and final-video scope

The user explicitly wants blue Gazebo LiDAR rays retained. No visualization,
sensor, launcher or rendering code is changed by this audit.

There were zero associated scan returns in 664 samples with nearby people,
and zero associated lethal costmap cells in 76 samples with a person in the
window. This recording therefore **does not establish Actor GPU-LiDAR
visibility**. It also does not prove invisibility: these are spatial
association diagnostics, not an actor/no-actor controlled comparison. Do not
claim a hard-obstacle wall or pathological double counting was demonstrated.

Actor count remains **one**. No 3/6/8/10-Actor trials, trajectories, performance
results or final launcher have been created. The user's automatic expansion
instruction was conditional on all ten checks passing. The final-video run
command is consequently not available yet; the existing one-Actor command
remains `./scripts/start_video1_animated_demo.sh`.

## Evidence integrity

The original generated logs and summary were read only and remain unmodified.
SHA-256:

| File | Hash |
| --- | --- |
| `summary.json` | `8116ff9ea0aba6caf69c1ba37f02ec69cf3b758cd923f02369929a5c46865b4a` |
| `observations.jsonl` | `19e36a546b34352724ba7ac55220320424d57aca165e19507ab8abbfcca646f3` |
| `runtime.log` | `e333f092e6ce4445c6c5b4617afa4279586db60a86f161f1706b5dff8bd42c56` |
| `dds_probe.json` | `0d2eb09f94e145875186b77ad5a65c78cbf02a25351ae782f99bb65278efbbaa` |
