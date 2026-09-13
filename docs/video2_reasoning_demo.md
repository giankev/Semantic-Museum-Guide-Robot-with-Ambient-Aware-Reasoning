# Video 2: semantic graph and deterministic reasoning

Run from the desktop terminal in the repository:

```bash
./scripts/start_video2_reasoning_demo.sh
```

Stop the owned Video 2 container:

```bash
./scripts/stop_video2_reasoning_demo.sh
```

The launcher stops previous owned Video 1/Video 2 demos, builds inside the
existing image, and opens Gazebo and RViz with exactly one walking Actor. It
reuses the accepted simulation launch, software-rendered server, NVIDIA GUI
selection and effective BT timeout of 200 ms. It never edits those components,
the museum world source, navigation parameters, or Video 1 scripts. Domain 108
(default) isolates this scene; `VIDEO2_ROS_DOMAIN_ID` can select another domain.
Startup and ROS logs go under `log/video2_reasoning/<run>/`; the terminal shows
only readiness progress and the concise semantic result. Gazebo/RViz remain
open after reasoning. No microphone, language model, network API or speech node
is involved. **Navigation does not start automatically.**

## Inventory inspected before selecting the request

These entities already exist in `museum_assistant/config/semantic_map.yaml`:

| Artwork | Style | `located_in` room | Existing physical route mapping |
|---|---|---|---|
| `monet_water_lilies` (Water Lilies, Claude Monet) | impressionism | impressionism_hall | north_gallery |
| `van_gogh_starry_night` (Starry Night Study, Vincent van Gogh) | post_impressionism | impressionism_hall | north_gallery |
| `roman_statue` (Roman Marble Statue) | classical | ancient_art_hall | south_west_gallery |
| `egyptian_vase` (Egyptian Funerary Vase) | ancient_egyptian | ancient_art_hall | south_west_gallery |
| `interactive_light_installation` (Museum Education Lab) | interactive | kids_hall | south_east_gallery |

The seven semantic areas are entrance, main_corridor, impressionism_hall,
ancient_art_hall, kids_hall, temporary_exhibition (closed), and exit. Only the
three mapped exhibition rooms have supplied-museum physical routes. Entrance
connects to main_corridor; main_corridor connects to each of the four exhibition
rooms and exit. Graph edges also include room `has_sensor` links and guide/staff
`can_update` links to room_status, crowd_level and noise_level. Artwork styles
and artists are attributes, not invented graph edges. The existing reasoner
supports style constraints; this demo does not claim artwork-title or artist
language parsing that this deterministic interface does not provide.

## Actual request and pipeline

Human-readable rendering of the injected input: **“I want to see classical art.”**
This sentence is a caption for a deterministic structured request, not text
processed by an NLP parser. Exactly one message is sent through the existing
`/museum/user_request` interface:

```json
{
  "request_id": "video2_request_1",
  "session_id": "session_1",
  "intent": "recommend_and_prepare_navigation",
  "constraints": {"style": "classical"}
}
```

The sole physics-backed Actor is `walker_1`. Its observed presence is passed to
the existing `VisitorSession.observe()` mechanism, which produces `visitor_1`
and active `session_1`; the result is published on `/museum/session_state` and
observed back by the monitor. This small identity adapter does not add graph
semantics or claim visual person recognition. The established readiness gate
checks Actor motion and Gazebo pose, /people, usable LiDAR, ACTIVE Nav2 and the
accepted critic parameters before input is sent. The gate's navigation method
is never called.

The unchanged `reasoning_node` validates the request with `StructuredRequest`,
queries the real semantic graph and updates session memory. Its actual response
contains `matching_artworks=[roman_statue]`, `selected_room=ancient_art_hall`
and `skill=navigate_to`. No unique-entity selector or candidate ranking beyond
these exposed fields is invented. The unchanged `semantic_route_dispatcher`
resolves that room through `supplied_museum_semantic_routes.yaml` and publishes
one `/museum/supplied_route_request` for `south_west_gallery`.

## Monitor sources and displayed facts

| Monitor field | Evidence source |
|---|---|
| Visitor/session | Existing VisitorSession output, received on `/museum/session_state`, activated by the observed Actor |
| Request/intent/style | The single injected JSON, also observed on `/museum/user_request` |
| Artwork style and `located_in` | `/museum/scene_graph` snapshot, checked against the response |
| Matching entities, selected room, action | `/museum/assistant_response` from the real reasoner |
| Physical destination | `/museum/supplied_route_request` from the real dispatcher |
| Final physical goal | Existing `load_route_plan()` and supplied route/layout YAML |
| SUCCESS | Correlated input/response/graph/route evidence; means preparation success, not navigation success |

Exact graph facts shown:

```text
roman_statue : style = classical
roman_statue -> located_in -> ancient_art_hall
```

The separate configuration mapping is shown explicitly as:

```text
ancient_art_hall -> south_west_gallery
```

The physical final pose is `x=-10.0, y=-21.5, yaw=1.5708`. The semantic map's
abstract room nav_pose is not misrepresented as the supplied-world goal. The
existing complete route contains south_entry, south_junction, south_inner_gap,
south_west_door_approach and candidate_south_west. No runner is started and no
Nav2 goal is sent: the monitor labels the action **PREPARED**.

## Validation

Real Docker/Gazebo run `20260913T124520Z_actor` completed reasoning SUCCESS:
one moving Actor, usable LiDAR (631 finite returns at readiness), ACTIVE Nav2,
one observed user request, one reasoner response, one route request, and the
non-north destination above. The terminal and raw topic messages are retained
in `reasoning_summary.json`, `reasoning_events.jsonl`, `readiness.log` and ROS
node logs. Gazebo and RViz remained open.

Six focused tests pass, including a counterfactual: replacing only `classical`
with `interactive` selects `interactive_light_installation` and
`south_east_gallery` at x=10. This verifies that presentation follows the real
reasoner and route data rather than hardcoding the selected result. Tests also
reject north_gallery, missing graph facts, mismatched request correlation and
session activation without an observed Actor. Another 31 existing reasoning,
route-dispatch, visitor-session and session-memory tests pass. The launch also
passes the existing seven Actor test groups. Video 1 and core files are unchanged.
