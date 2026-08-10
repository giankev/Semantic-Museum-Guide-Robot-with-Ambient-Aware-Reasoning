# Final benchmark framework

This directory turns existing, validated project diagnostics into manually
readable CSV tables, a provenance-aware summary, and report-ready plots. It is
an evaluation layer only: it does not introduce a robot algorithm, ROS node,
experiment manager, or alternative recorder.

## Research questions

1. **Navigation:** does TIAGo reliably reach all four supplied-museum zones?
2. **Social navigation:** how do DWB baseline, isotropic
   `ProxemicForceCritic`, and its opt-in velocity-aligned anisotropic mode
   compare on clearance from the front of the same moving person without
   compromising task completion?
3. **Scene graph reasoning:** does the bounded deterministic reasoner select
   the expected destination and respond to ambient-state changes?
4. **Language:** do the bounded Italian/English cases produce the expected
   intent and constraints and obey the route policy?
5. **Escort:** do normal, lag/resume, and lost scenarios produce the required
   transitions and navigation cancellation behavior?
6. **End-to-end:** does real WAV input reach successful reasoning, semantic
   grounding, social Nav2 execution, escort `arrived`, and zero terminal
   velocity?
7. **Session memory:** does the runtime scene graph preserve a destination for
   one session, isolate other sessions, and revalidate ambient constraints
   before a deictic follow-up route?
8. **Engagement:** do bounded visual-only, LiDAR-only, passing, far, stationary,
   and leaving sequences produce the expected deterministic engagement state?

Following the AirporTiago evaluation philosophy, this framework does not
re-benchmark established external algorithms in isolation. It evaluates the
modules developed in this project and, especially, their integration.

## Data layout and provenance

- `raw/*.csv` contains one row per observed case or runtime execution.
- `summary/benchmark_summary.json` contains aggregates, configuration
  provenance, run counts, and limitations.
- `summary/benchmark_summary.csv` is a flat report-table view.
- `plots/*.png` contains the five required publication-style figures.

Most raw rows contain `run_id`, `timestamp_utc`, `git_commit`, `benchmark`,
`scenario`, `variant`, and `status`. Older diagnostics that did not record a
commit retain `git_commit=NA`; the framework never substitutes the current
commit for unknown historical provenance. Missing metrics remain empty/NA.
Credentials, authorization headers, and raw audio are never imported.
`engagement.csv` intentionally uses the smaller case schema documented in the
engagement feature specification.

`import-existing` conservatively selects the newest complete, all-PASS
navigation batch whose reports contain the final localization and terminal
command gates. It imports final end-to-end PASS reports directly. Social runs
are imported only from raw JSON produced by
`compare_supplied_museum_social_force.py`; numeric values documented only in
prose are intentionally not reconstructed.

## Commands

Create an isolated tooling environment first. `networkx` and `PyYAML` are
needed by the two existing offline benchmarks; `matplotlib` is needed only for
the plots. This environment is not part of the robot image or ROS workspace:

```bash
python3 -m venv /tmp/museum-benchmark-venv
/tmp/museum-benchmark-venv/bin/pip install \
  networkx==2.8.8 PyYAML==6.0.2 matplotlib==3.7.5
export PATH=/tmp/museum-benchmark-venv/bin:$PATH
```

Then, from the repository root:

```bash
python3 scripts/final_benchmark.py import-existing
python3 scripts/final_benchmark.py offline
python3 scripts/final_benchmark.py summarize
python3 scripts/final_benchmark.py plot
python3 scripts/final_benchmark.py status
```

`offline` runs only the scene-graph, language, session-memory, and engagement
logic benchmarks.
These are reported as a **bounded deterministic functional benchmark**, a
**bounded functional language benchmark**, and a **bounded session-memory
functional benchmark**, not as general AI or dialogue accuracy. The language
benchmark is not a Whisper WER evaluation; live cloud STT is integration
evidence only. Its eight session-memory cases are exported case-by-case to
`raw/session_memory.csv`.

## Physical campaign design

The framework never starts Gazebo. Missing navigation runs can be recorded by
the existing acceptance runner; this exact command requests three repetitions
of each destination in one campaign:

```bash
./scripts/supplied_museum_navigation_acceptance.sh \
  central_gallery central_gallery central_gallery \
  north_gallery north_gallery north_gallery \
  south_west_gallery south_west_gallery south_west_gallery \
  south_east_gallery south_east_gallery south_east_gallery
```

The social experiment uses clean `north_gallery` triplets with the same world,
robot start, scripted visitor behavior, and deterministic moving-person
trajectory. Start the existing supplied reasoning launch for the baseline:

```bash
ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py \
  gzclient:=False publish_people:=True
```

After clean restarts, launch the isotropic and anisotropic variants:

```bash
ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py \
  gzclient:=False publish_people:=True \
  nav2_params_file:=$(ros2 pkg prefix museum_assistant)/share/museum_assistant/config/nav2_supplied_social_force.yaml

ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py \
  gzclient:=False publish_people:=True \
  nav2_params_file:=$(ros2 pkg prefix museum_assistant)/share/museum_assistant/config/nav2_supplied_anisotropic.yaml
```

In the corresponding container, record each run with:

```bash
python3 scripts/compare_supplied_museum_social_force.py record \
  --variant baseline --request-id triplet_1_baseline --moving-person \
  --output .navigation_diagnostics/social_triplet_1/baseline.json

python3 scripts/compare_supplied_museum_social_force.py record \
  --variant isotropic --request-id triplet_1_isotropic --moving-person \
  --output .navigation_diagnostics/social_triplet_1/isotropic.json

python3 scripts/compare_supplied_museum_social_force.py record \
  --variant anisotropic --request-id triplet_1_anisotropic --moving-person \
  --output .navigation_diagnostics/social_triplet_1/anisotropic.json
```

The default trajectory moves `guide_1` from `(1.4, 16.0)` at `(0.0, -0.12)`
m/s, beginning with the first active Nav2 goal. Repeat with fresh starts for
five target triplets, or three triplets for the minimum campaign. The primary
metrics are minimum total and front-person distance; time, path length,
success, recoveries, and no-progress failures are secondary. ADE/FDE and
small-N inferential tests are deliberately excluded.

Escort coverage requires at least one physical result for `normal`,
`lag_resume`, and `lost`. The current scripted full-stack acceptance provides
the lag/resume case. Normal and lost remain explicitly missing until equivalent
validated diagnostics exist; the aggregator does not infer them from unit
tests or invent physical results.

Record end-to-end integration evidence with the existing runner:

```bash
FINAL_SKIP_DOCKER_BUILD=1 \
./scripts/final_end_to_end_acceptance.sh ~/phase8_request.wav
```

The target is three complete runs. The WAV stays outside `benchmarks/`.

## Metrics and report-ready outputs

Navigation reports success rate plus mean/std time, physical path length,
Gazebo final error, AMCL final error, and total recoveries when recorded.
Social reports the three paired deltas (isotropic−baseline,
anisotropic−isotropic, and anisotropic−baseline), percentage improvement,
plus variant-level success, time, and path length. Reasoning and language preserve
all case-level expectations and predictions. Session memory reports write,
follow-up, isolation, explicit override, ambient revalidation, route policy,
and repeatability. Escort and end-to-end preserve the public state/action
evidence needed for audit.

The flat summary CSV is ready for report tables. The five PNGs cover navigation
error/time, paired social clearance, social task efficiency, and bounded
reasoning/language accuracy. Every plot labels units and N; when no compatible
social triplet exists, the plot says `N=0` instead of displaying fabricated data.

## Limitations

The generated JSON records the required limitations: simulation-only
evaluation, scripted/non-reactive people, small physical paired N, simulated
visitor observation, external Groq STT, and the absence of a real-user
subjective study.
