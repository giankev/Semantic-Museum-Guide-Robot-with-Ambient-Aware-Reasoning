# Supplied museum reasoning-to-navigation integration

This phase connects the existing deterministic reasoner to the validated
supplied-museum route runner. It deliberately does not launch the escort
runtime and does not change the accepted Nav2, AMCL, DWB, map, world collision,
route-coordinate, or candidate-coordinate configuration.

The runtime chain is:

```text
/museum/user_request
  -> reasoning_node
  -> /museum/assistant_response
  -> semantic_route_dispatcher
  -> /museum/supplied_route_request
  -> supplied_museum_route_runner
  -> serialized NavigateToPose actions
  -> /museum/navigation_result
```

`config/supplied_museum_semantic_routes.yaml` is the only semantic-to-physical
mapping. The resolver validates it at dispatcher startup against the semantic
graph, the supplied route YAML, and the supplied room-layout YAML. Python code
contains no copied route coordinates. The old-museum `nav_pose` values remain
in `semantic_map.yaml` for the older demo, but this supplied-museum chain ignores
them and resolves only `selected_room`.

The physical mapping is:

```text
impressionism_hall -> north_gallery      -> candidate_north
ancient_art_hall   -> south_west_gallery -> candidate_south_west
kids_hall          -> south_east_gallery -> candidate_south_east
```

Only `supplied_museum_route_runner` creates Nav2 action clients in this launch.
`semantic_route_dispatcher` publishes one correlated route request and rejects
duplicate decisions; it never sends a Nav2 goal. The runner publishes success
only after Nav2 succeeds at the configured final candidate and synchronized
Gazebo error is at most 0.50 m.

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
  gzclient:=False
```

After Nav2 becomes active, run the correlated probe for impressionism:

```bash
python3 /root/exchange/scripts/run_supplied_museum_reasoning_episode.py \
  --request-id runtime_impressionism --session-id acceptance_session \
  --style impressionism --expected-room impressionism_hall \
  --expected-route north_gallery --expected-candidate candidate_north \
  --output /root/exchange/.navigation_diagnostics/impressionism.json
```

Use a fresh launch for the southern episode and replace the case-specific
arguments with `classical`, `ancient_art_hall`, `south_west_gallery`, and
`candidate_south_west`. The probe publishes only `/museum/user_request`; a test
that publishes `/museum/supplied_route_request` directly does not validate this
integration.
