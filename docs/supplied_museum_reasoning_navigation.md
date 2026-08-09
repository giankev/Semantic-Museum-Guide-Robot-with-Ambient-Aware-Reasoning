# Supplied museum reasoning-to-navigation integration

This phase connects the existing deterministic reasoner and escort supervisor
to the validated supplied-museum route runner. It does not change the accepted
Nav2, AMCL, DWB, map, world collision, route-coordinate, or
candidate-coordinate configuration.

The runtime chain is:

```text
[audio file -> speech_to_text_node -> /museum/user_text -> language_node ->]
  /museum/user_request
  -> reasoning_node
  -> /museum/assistant_response
  -> semantic_route_dispatcher
  -> /museum/supplied_route_request
  -> supplied_museum_route_runner
  <-> /museum/visitor_observation and /museum/escort_state
  -> serialized NavigateToPose actions
  -> /museum/navigation_result
```

`config/supplied_museum_semantic_routes.yaml` is the only semantic-to-route
mapping. The request sent to the runner contains only `request_id`, `session_id`,
`selected_room`, and `route`. The runner loads waypoint names, poses, and the
final candidate from `supplied_museum_routes.yaml`; they are not copied into the
request. The old-museum `nav_pose` values remain in `semantic_map.yaml` for the
older demo, but this supplied-museum chain ignores them.

The physical mapping is:

```text
impressionism_hall -> north_gallery
ancient_art_hall   -> south_west_gallery
kids_hall          -> south_east_gallery
```

Only `supplied_museum_route_runner` creates Nav2 action clients in this launch.
`semantic_route_dispatcher` publishes one correlated route request and rejects
duplicate decisions; it never sends a Nav2 goal. The runner publishes success
only after Nav2 succeeds at the configured final candidate and synchronized
Gazebo error is at most 0.50 m.

The launch also reuses `visitor_session_node` and `scripted_visitor_node`.
Escort WAITING cancels the current runner-owned goal without failing the route;
ESCORTING resumes the same waypoint, and LOST cancels without automatic resume.
The scripted visitor acceptance is limited to the straight `north_gallery`
route because the marker does not plan around walls.

## Offline verification

Run inside the project container after sourcing the workspace:

```bash
python3 /root/exchange/scripts/verify_supplied_museum_reasoning.py
```

This checks impressionism, classical, and child-friendly decisions without
Gazebo, an external API, or an LLM.

## Runtime verification

Start a clean end-to-end episode:

```bash
ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py \
  gzclient:=False use_language:=True use_speech:=True publish_people:=True \
  nav2_params_file:=$(ros2 pkg prefix museum_assistant)/share/museum_assistant/config/nav2_supplied_social_force.yaml
```

After Nav2 becomes active, run the correlated probe for impressionism:

```bash
python3 /root/exchange/scripts/run_supplied_museum_reasoning_episode.py \
  --request-id text_1 --session-id session_1 \
  --style impressionism --avoid-crowd \
  --audio-file /path/inside/container/request.wav \
  --expected-transcript \
    "Portami a vedere qualcosa di impressionista evitando la folla" \
  --expected-room impressionism_hall \
  --expected-route north_gallery --expected-candidate candidate_north \
  --expected-escort-sequence escorting waiting escorting arrived \
  --expected-navigation-sequence accepted \
    intentionally_canceled_for_escort_wait accepted succeeded \
  --output /root/exchange/.navigation_diagnostics/impressionism.json
```

With `--audio-file`, the probe publishes only `/museum/audio_file`, captures
the single `/museum/user_text` transcription and generated
`/museum/user_request`, and verifies both occur once. `GROQ_API_KEY` and a real
Italian recording are required. The existing `--text` and direct structured
request modes remain available. Publishing directly to
`/museum/supplied_route_request` does not validate this integration. Do not use
the direct-follow scripted visitor as acceptance evidence for southern routes.
