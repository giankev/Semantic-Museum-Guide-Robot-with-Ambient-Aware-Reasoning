import json
from pathlib import Path
import threading
import time
from types import SimpleNamespace

import pytest

from museum_assistant.language_parser import parse_deterministic
from museum_assistant.speech_to_text import (
    DEFAULT_GROQ_STT_MODEL,
    GROQ_STT_TIMEOUT_SECONDS,
    MAX_AUDIO_FILE_BYTES,
    GroqTranscriptionClient,
    SpeechToTextError,
    TranscriptionCoordinator,
    TranscriptionOutcome,
    publication_data,
    validate_audio_path,
)


def write_audio(path: Path, content: bytes = b"not decoded in unit tests") -> Path:
    path.write_bytes(content)
    return path


def assert_status(expected, callable_, *args):
    with pytest.raises(SpeechToTextError) as caught:
        callable_(*args)
    assert caught.value.status == expected


def test_supported_wav_file_is_accepted(tmp_path):
    audio = validate_audio_path(str(write_audio(tmp_path / "sample.wav")))

    assert audio.extension == ".wav"
    assert audio.basename == "sample.wav"


@pytest.mark.parametrize("extension", [".m4a", ".MP3"])
def test_other_supported_audio_extensions_are_accepted(tmp_path, extension):
    audio = validate_audio_path(str(write_audio(tmp_path / f"sample{extension}")))

    assert audio.extension == extension.lower()


def test_missing_file_is_rejected_before_sdk_construction(tmp_path):
    factory_called = False

    def factory(**_kwargs):
        nonlocal factory_called
        factory_called = True

    client = GroqTranscriptionClient("unit-key", openai_factory=factory)
    assert_status(
        "file_not_found", client.transcribe, str(tmp_path / "missing.wav")
    )
    assert factory_called is False


def test_directory_path_is_rejected(tmp_path):
    assert_status("not_regular_file", validate_audio_path, str(tmp_path))


def test_unsupported_extension_is_rejected(tmp_path):
    path = write_audio(tmp_path / "notes.txt")
    assert_status("unsupported_audio_format", validate_audio_path, str(path))


def test_empty_file_is_rejected(tmp_path):
    path = write_audio(tmp_path / "empty.ogg", b"")
    assert_status("empty_audio_file", validate_audio_path, str(path))


def test_oversized_sparse_file_is_rejected(tmp_path):
    path = tmp_path / "large.flac"
    with path.open("wb") as stream:
        stream.truncate(MAX_AUDIO_FILE_BYTES + 1)

    assert_status("audio_file_too_large", validate_audio_path, str(path))


def test_missing_api_key_is_safe_and_does_not_construct_sdk(tmp_path):
    path = write_audio(tmp_path / "sample.wav")
    factory_called = False

    def factory(**_kwargs):
        nonlocal factory_called
        factory_called = True

    client = GroqTranscriptionClient(None, openai_factory=factory)
    assert_status("missing_api_key", client.transcribe, str(path))
    assert factory_called is False


def make_recording_factory(response_text=" transcript ", provider_error=None):
    record = {"init": None, "create": None, "file_was_open": None}

    class Transcriptions:
        def create(self, **kwargs):
            record["create"] = kwargs
            record["file_was_open"] = not kwargs["file"].closed
            if provider_error is not None:
                raise provider_error
            return SimpleNamespace(text=response_text)

    def factory(**kwargs):
        record["init"] = kwargs
        return SimpleNamespace(
            audio=SimpleNamespace(transcriptions=Transcriptions())
        )

    return factory, record


def test_successful_fake_transcription_returns_stripped_text(tmp_path):
    path = write_audio(tmp_path / "sample.m4a")
    factory, _record = make_recording_factory("  Testo italiano.  ")
    client = GroqTranscriptionClient("unit-key", openai_factory=factory)

    assert client.transcribe(str(path)).text == "Testo italiano."


def test_whitespace_only_transcription_is_rejected(tmp_path):
    path = write_audio(tmp_path / "sample.wav")
    factory, _record = make_recording_factory(" \n\t ")
    client = GroqTranscriptionClient("unit-key", openai_factory=factory)

    assert_status("empty_transcription", client.transcribe, str(path))


def test_provider_exception_fails_closed(tmp_path):
    path = write_audio(tmp_path / "sample.mp3")
    factory, _record = make_recording_factory(
        provider_error=RuntimeError("provider failed")
    )
    client = GroqTranscriptionClient("unit-key", openai_factory=factory)

    assert_status("transcription_api_error", client.transcribe, str(path))


def test_exact_sdk_configuration_and_transcription_arguments(tmp_path):
    path = write_audio(tmp_path / "sample.webm")
    factory, record = make_recording_factory()
    client = GroqTranscriptionClient("unit-key", openai_factory=factory)

    client.transcribe(str(path))

    assert record["init"] == {
        "api_key": "unit-key",
        "base_url": "https://api.groq.com/openai/v1",
        "timeout": GROQ_STT_TIMEOUT_SECONDS,
        "max_retries": 0,
    }
    assert record["file_was_open"] is True
    assert record["create"]["model"] == "whisper-large-v3-turbo"
    assert record["create"]["language"] == "it"
    assert record["create"]["response_format"] == "json"
    assert record["create"]["temperature"] == 0.0
    assert record["create"]["file"].closed is True
    assert DEFAULT_GROQ_STT_MODEL == "whisper-large-v3-turbo"


def test_publication_boundary_emits_text_only_for_success():
    success = TranscriptionOutcome(
        audio_request_id="audio_1",
        status="success",
        model=DEFAULT_GROQ_STT_MODEL,
        audio_basename="sample.wav",
        transcript="Portami al museo",
    )
    failure = TranscriptionOutcome(
        audio_request_id="audio_2",
        status="transcription_api_error",
        model=DEFAULT_GROQ_STT_MODEL,
        audio_basename="sample.wav",
    )

    success_status, success_text = publication_data(success)
    failure_status, failure_text = publication_data(failure)

    assert json.loads(success_status)["status"] == "success"
    assert success_text == "Portami al museo"
    assert json.loads(failure_status)["status"] == "transcription_api_error"
    assert failure_text is None


def poll_until_ready(coordinator, timeout=1.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        outcome = coordinator.poll()
        if outcome is not None:
            return outcome
        time.sleep(0.01)
    raise AssertionError("worker result was not ready")


def test_busy_rejection_and_request_ids_are_deterministic():
    release = threading.Event()

    class BlockingClient:
        model = DEFAULT_GROQ_STT_MODEL

        def transcribe(self, _path):
            release.wait(timeout=1.0)
            raise SpeechToTextError("transcription_api_error")

    coordinator = TranscriptionCoordinator(BlockingClient())

    assert coordinator.submit("first.wav") is None
    busy = coordinator.submit("second.wav")
    assert busy.audio_request_id == "audio_2"
    assert busy.status == "busy"

    release.set()
    first = poll_until_ready(coordinator)
    assert first.audio_request_id == "audio_1"

    assert coordinator.submit("third.wav") is None
    third = poll_until_ready(coordinator)
    assert third.audio_request_id == "audio_3"


def test_coordinator_remains_usable_after_api_failure():
    class FailingClient:
        model = DEFAULT_GROQ_STT_MODEL

        def transcribe(self, _path):
            raise RuntimeError("unexpected client failure")

    coordinator = TranscriptionCoordinator(FailingClient())
    assert coordinator.submit("first.wav") is None
    first = poll_until_ready(coordinator)
    assert first.status == "transcription_api_error"

    assert coordinator.submit("second.wav") is None
    second = poll_until_ready(coordinator)
    assert second.status == "transcription_api_error"
    assert second.audio_request_id == "audio_2"


def test_phase7_deterministic_navigation_parser_remains_available():
    candidate = parse_deterministic(
        "Portami a vedere qualcosa di impressionista"
    )

    assert candidate == {
        "resolved": True,
        "intent": "recommend_and_prepare_navigation",
        "constraints": {"style": "impressionism"},
    }
