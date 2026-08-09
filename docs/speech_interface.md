# Bounded File-Based Speech Interface

## Scope

Phase 8 adds a file-based speech-to-text boundary in front of the Phase 7
language pipeline:

```text
audio file path -> speech_to_text_node -> Groq audio transcription
                -> /museum/user_text -> language_node
                -> /museum/user_request -> reasoning_node
                -> /museum/assistant_response
```

This prototype accepts one existing WAV or other supported audio file path
visible inside the container. It does not capture a microphone, stream audio, detect wake words
or voice activity, manage dialogue, synthesize speech, play audio, or perform
local speech recognition.

## ROS Interface

| Topic | Type | Direction | Content |
| --- | --- | --- | --- |
| `/museum/audio_file` | `std_msgs/msg/String` | input | Container-visible audio file path. |
| `/museum/transcription_status` | `std_msgs/msg/String` | output | JSON status and safe request metrics. |
| `/museum/user_text` | `std_msgs/msg/String` | output | Stripped transcript, published only on success. |

Request IDs are process-local and deterministic: `audio_1`, `audio_2`, and so
on. The node accepts only one transcription at a time. A second input receives
`status=busy`; the active synchronous cloud request remains in one daemon
worker thread, while ROS publications happen from an executor timer.

Failures publish status JSON but never `/museum/user_text`. Expected statuses
include `invalid_path`, `file_not_found`, `not_regular_file`,
`unreadable_audio_file`, `unsupported_audio_format`, `empty_audio_file`,
`audio_file_too_large`, `missing_api_key`, `transcription_api_error`, and
`empty_transcription`.

## Provider Boundary

The default transcription model is `whisper-large-v3-turbo`, configured
separately with `GROQ_STT_MODEL`. The node uses `GROQ_API_KEY` and defaults
`GROQ_BASE_URL` to `https://api.groq.com/openai/v1`. It does not reuse or
change the Phase 7 `GROQ_MODEL=openai/gpt-oss-20b` setting.

The pinned `openai==2.46.0` client call is:

```python
client = OpenAI(
    api_key=api_key,
    base_url=base_url,
    timeout=20.0,
    max_retries=0,
)
with open(audio_path, "rb") as audio_file:
    transcription = client.audio.transcriptions.create(
        file=audio_file,
        model=model,
        language="it",
        response_format="json",
        temperature=0.0,
    )
```

Only `transcription.text` is used. No timestamps, translation, diarization,
segments, or verbose provider response are requested.

Supported extensions are `.wav`, `.mp3`, `.mp4`, `.mpeg`, `.mpga`, `.m4a`,
`.ogg`, `.flac`, and `.webm`. Files must be regular, readable, non-empty, and
at most 25 MB. The node does not convert audio and does not require `ffmpeg`.
It starts normally without `GROQ_API_KEY`; a valid file then produces
`missing_api_key` and the node remains alive.

## Privacy Limitation

This prototype sends the selected audio file to the configured external Groq
cloud transcription provider. It is not offline speech recognition and does
not provide production privacy guarantees. Do not use recordings beyond the
consent and data-handling constraints of the project and provider. The live
runner copies the recording into ignored `.phase8_acceptance_tmp/`, never
prints or stores the key, and removes the copied recording on success or
failure.

## Build And Test

Inside the project container:

```bash
cd /root/exchange/exchange/museum_ws
source /opt/ros/humble/setup.bash
source /root/tiago_public_ws/install/setup.bash
source /root/social_nav_ws/install/setup.bash

colcon build --symlink-install \
  --packages-select museum_assistant museum_social_critic
source install/setup.bash
colcon test --packages-select museum_assistant museum_social_critic
colcon test-result --verbose
```

The focused unit and coordinator tests are ROS-independent and make no
Internet requests. They use a generated WAV and a fake provider to verify one
successful Italian transcription, one publication outcome, empty-audio
suppression, provider-failure suppression, and the unchanged language-parser
boundary.

Run the operator-supplied Italian recording through the complete headless
acceptance chain with:

```bash
scripts/phase8_live_acceptance.sh /path/to/recording.wav
```

To reuse an already available local `museum-tiago:humble` image and skip the
potentially slow Docker build:

```bash
PHASE8_SKIP_DOCKER_BUILD=1 \
./scripts/phase8_live_acceptance.sh ~/phase8_request.wav
```

This mode fails before starting the acceptance container if the local image is
missing. Without `PHASE8_SKIP_DOCKER_BUILD=1`, the runner keeps rebuilding the
image as before.

By default, the Phase 8 runner builds the image and packages, runs automated
tests, checks model access, starts only `speech_to_text_node`, `language_node`, and
`reasoning_node`, and exercises success, nonexistent-file, unsupported-format,
and missing-key behavior. Gazebo, Nav2, escort, people publishers, social
navigation, microphone streaming, and TTS are not started by that bounded
runner.

The complete supplied-museum launch can include this same speech node without
changing the downstream interfaces:

```bash
ros2 launch museum_assistant supplied_museum_reasoning_navigation.launch.py \
  gzclient:=False use_language:=True use_speech:=True publish_people:=True \
  nav2_params_file:=$(ros2 pkg prefix museum_assistant)/share/museum_assistant/config/nav2_supplied_social_force.yaml
```

With `GROQ_API_KEY` configured, publish a container-visible recording through
the correlated physical-episode probe:

```bash
python3 /root/exchange/scripts/run_supplied_museum_reasoning_episode.py \
  --request-id text_1 --session-id session_1 --style impressionism \
  --avoid-crowd --audio-file /path/inside/container/request.wav \
  --expected-transcript \
    "Portami a vedere qualcosa di impressionista evitando la folla" \
  --expected-room impressionism_hall --expected-route north_gallery \
  --expected-candidate candidate_north \
  --expected-escort-sequence escorting waiting escorting arrived \
  --expected-navigation-sequence accepted \
    intentionally_canceled_for_escort_wait accepted succeeded \
  --output /root/exchange/.navigation_diagnostics/speech_north.json
```

The probe publishes only the audio path, then requires exactly one transcript,
one matching StructuredRequest, one route request, a reasoning decision,
`candidate_north`, successful Nav2 completion, and escort `arrived`.

## Runtime Result

Implementation and automated acceptance pass. Live audio acceptance remains
pending an operator-provided recording containing "Portami a vedere qualcosa
di impressionista evitando la folla" and a configured Groq key. Headless negative ROS checks
pass for nonexistent files, unsupported formats, and a missing key: all
publish zero user texts and leave the node alive. Do not describe Phase 8 as
the runtime-validated bounded file-based speech-to-text prototype until the
positive live-audio chain succeeds.
