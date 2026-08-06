"""Bounded file validation and Groq-compatible audio transcription."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import queue
import threading
import time
from typing import Callable, Optional


DEFAULT_GROQ_STT_MODEL = "whisper-large-v3-turbo"
DEFAULT_GROQ_BASE_URL = "https://api.groq.com/openai/v1"
GROQ_STT_TIMEOUT_SECONDS = 20.0
MAX_AUDIO_FILE_BYTES = 25 * 1024 * 1024
SUPPORTED_AUDIO_EXTENSIONS = frozenset(
    {".wav", ".mp3", ".mp4", ".mpeg", ".mpga", ".m4a", ".ogg", ".flac", ".webm"}
)


@dataclass(frozen=True)
class ValidatedAudioFile:
    path: Path
    basename: str
    size_bytes: int
    extension: str


class SpeechToTextError(Exception):
    """Expected local or provider failure with a public status code."""

    def __init__(
        self,
        status: str,
        *,
        audio_basename: str = "",
        file_size_bytes: Optional[int] = None,
    ) -> None:
        super().__init__(status)
        self.status = status
        self.audio_basename = audio_basename
        self.file_size_bytes = file_size_bytes


@dataclass(frozen=True)
class Transcription:
    text: str
    audio: ValidatedAudioFile


@dataclass(frozen=True)
class TranscriptionOutcome:
    audio_request_id: str
    status: str
    model: str
    audio_basename: str = ""
    file_size_bytes: Optional[int] = None
    latency_seconds: Optional[float] = None
    transcript: Optional[str] = None

    def status_data(self) -> dict:
        data = {
            "audio_request_id": self.audio_request_id,
            "status": self.status,
            "model": self.model,
        }
        if self.audio_basename:
            data["audio_basename"] = self.audio_basename
        if self.file_size_bytes is not None:
            data["file_size_bytes"] = self.file_size_bytes
        if self.latency_seconds is not None:
            data["latency_seconds"] = round(self.latency_seconds, 3)
        if self.transcript is not None:
            data["transcript_characters"] = len(self.transcript)
        return data

    def status_json(self) -> str:
        return json.dumps(self.status_data(), sort_keys=True)


def publication_data(
    outcome: TranscriptionOutcome,
) -> tuple[str, Optional[str]]:
    """Return status JSON and the optional text publication payload."""
    transcript = outcome.transcript if outcome.status == "success" else None
    return outcome.status_json(), transcript


def safe_audio_basename(audio_path: object) -> str:
    if not isinstance(audio_path, str) or not audio_path.strip():
        return ""
    try:
        return Path(audio_path.strip()).name
    except (OSError, ValueError):
        return ""


def validate_audio_path(audio_path: object) -> ValidatedAudioFile:
    """Resolve and validate one endpoint-compatible audio file."""
    if not isinstance(audio_path, str) or not audio_path.strip():
        raise SpeechToTextError("invalid_path")

    basename = safe_audio_basename(audio_path)
    try:
        resolved = Path(audio_path.strip()).expanduser().resolve(strict=False)
    except (OSError, RuntimeError, ValueError):
        raise SpeechToTextError(
            "invalid_path", audio_basename=basename
        ) from None

    try:
        if not resolved.exists():
            raise SpeechToTextError(
                "file_not_found", audio_basename=basename
            )
        if not resolved.is_file():
            raise SpeechToTextError(
                "not_regular_file", audio_basename=basename
            )
        if not os.access(resolved, os.R_OK):
            raise SpeechToTextError(
                "unreadable_audio_file", audio_basename=basename
            )

        extension = resolved.suffix.lower()
        if extension not in SUPPORTED_AUDIO_EXTENSIONS:
            raise SpeechToTextError(
                "unsupported_audio_format", audio_basename=basename
            )

        size_bytes = resolved.stat().st_size
    except SpeechToTextError:
        raise
    except OSError:
        raise SpeechToTextError(
            "invalid_path", audio_basename=basename
        ) from None

    if size_bytes == 0:
        raise SpeechToTextError(
            "empty_audio_file",
            audio_basename=basename,
            file_size_bytes=size_bytes,
        )
    if size_bytes > MAX_AUDIO_FILE_BYTES:
        raise SpeechToTextError(
            "audio_file_too_large",
            audio_basename=basename,
            file_size_bytes=size_bytes,
        )

    return ValidatedAudioFile(
        path=resolved,
        basename=basename,
        size_bytes=size_bytes,
        extension=extension,
    )


class GroqTranscriptionClient:
    """Minimal OpenAI-compatible client for one bounded transcription call."""

    def __init__(
        self,
        api_key: Optional[str],
        *,
        base_url: str = DEFAULT_GROQ_BASE_URL,
        model: str = DEFAULT_GROQ_STT_MODEL,
        timeout: float = GROQ_STT_TIMEOUT_SECONDS,
        openai_factory: Optional[Callable] = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url
        self.model = model
        self.timeout = timeout
        self._openai_factory = openai_factory

    def transcribe(self, audio_path: object) -> Transcription:
        audio = validate_audio_path(audio_path)
        if not isinstance(self.api_key, str) or not self.api_key.strip():
            raise SpeechToTextError(
                "missing_api_key",
                audio_basename=audio.basename,
                file_size_bytes=audio.size_bytes,
            )

        try:
            factory = self._openai_factory
            if factory is None:
                from openai import OpenAI

                factory = OpenAI
            client = factory(
                api_key=self.api_key,
                base_url=self.base_url,
                timeout=self.timeout,
                max_retries=0,
            )
            with audio.path.open("rb") as audio_file:
                response = client.audio.transcriptions.create(
                    file=audio_file,
                    model=self.model,
                    language="it",
                    response_format="json",
                    temperature=0.0,
                )
        except SpeechToTextError:
            raise
        except Exception:
            raise SpeechToTextError(
                "transcription_api_error",
                audio_basename=audio.basename,
                file_size_bytes=audio.size_bytes,
            ) from None

        text = getattr(response, "text", None)
        if not isinstance(text, str) or not text.strip():
            raise SpeechToTextError(
                "empty_transcription",
                audio_basename=audio.basename,
                file_size_bytes=audio.size_bytes,
            )
        return Transcription(text=text.strip(), audio=audio)


class TranscriptionCoordinator:
    """Own one worker and queue completed results for an executor thread."""

    def __init__(
        self,
        client: GroqTranscriptionClient,
        *,
        thread_factory: Callable = threading.Thread,
    ) -> None:
        self.client = client
        self._thread_factory = thread_factory
        self._request_number = 0
        self._busy = False
        self._lock = threading.Lock()
        self._results = queue.SimpleQueue()

    @property
    def busy(self) -> bool:
        with self._lock:
            return self._busy

    def submit(self, audio_path: object) -> Optional[TranscriptionOutcome]:
        with self._lock:
            self._request_number += 1
            request_id = f"audio_{self._request_number}"
            if self._busy:
                return TranscriptionOutcome(
                    audio_request_id=request_id,
                    status="busy",
                    model=self.client.model,
                    audio_basename=safe_audio_basename(audio_path),
                )
            self._busy = True

        worker = self._thread_factory(
            target=self._run,
            args=(audio_path, request_id),
            daemon=True,
            name="museum_groq_transcription",
        )
        worker.start()
        return None

    def _run(self, audio_path: object, request_id: str) -> None:
        started = time.monotonic()
        try:
            transcription = self.client.transcribe(audio_path)
            outcome = TranscriptionOutcome(
                audio_request_id=request_id,
                status="success",
                model=self.client.model,
                audio_basename=transcription.audio.basename,
                file_size_bytes=transcription.audio.size_bytes,
                latency_seconds=time.monotonic() - started,
                transcript=transcription.text,
            )
        except SpeechToTextError as exc:
            outcome = TranscriptionOutcome(
                audio_request_id=request_id,
                status=exc.status,
                model=self.client.model,
                audio_basename=(
                    exc.audio_basename or safe_audio_basename(audio_path)
                ),
                file_size_bytes=exc.file_size_bytes,
                latency_seconds=time.monotonic() - started,
            )
        except Exception:
            outcome = TranscriptionOutcome(
                audio_request_id=request_id,
                status="transcription_api_error",
                model=self.client.model,
                audio_basename=safe_audio_basename(audio_path),
                latency_seconds=time.monotonic() - started,
            )
        self._results.put(outcome)

    def poll(self) -> Optional[TranscriptionOutcome]:
        try:
            outcome = self._results.get_nowait()
        except queue.Empty:
            return None
        with self._lock:
            self._busy = False
        return outcome
