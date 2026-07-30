"""Minimal in-memory session logic for the static simulated visitor."""

from collections.abc import Collection

from museum_assistant.contracts import (
    PersonTrack,
    SessionLifecycle,
    SessionState,
)


class VisitorSession:
    """Map one internal simulator model name to one visitor session."""

    def __init__(
        self,
        simulator_model_name: str,
        track_id: str = "visitor_1",
        session_id: str = "session_1",
    ):
        self._simulator_model_name = simulator_model_name
        self._track = PersonTrack(track_id)
        self._session_id = session_id
        self.current_session: SessionState | None = None

    def observe(self, simulator_model_names: Collection[str]) -> SessionState | None:
        if self._simulator_model_name not in simulator_model_names:
            return None

        if self.current_session is None:
            self.current_session = SessionState(
                session_id=self._session_id,
                track_id=self._track.track_id,
                state=SessionLifecycle.ACTIVE,
            )

        return self.current_session
