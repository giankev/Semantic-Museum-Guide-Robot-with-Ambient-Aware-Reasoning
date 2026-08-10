"""Minimal in-memory session logic for the static simulated visitor."""

import math
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

    @property
    def session_id(self) -> str:
        return self._session_id

    @property
    def track_id(self) -> str:
        return self._track.track_id

    def observe(self, simulator_model_names: Collection[str]) -> SessionState | None:
        if self._simulator_model_name not in simulator_model_names:
            return None

        return self.activate()

    def activate(self) -> SessionState:
        """Activate the generic current-interlocutor session."""

        if self.current_session is None:
            self.current_session = SessionState(
                session_id=self._session_id,
                track_id=self._track.track_id,
                state=SessionLifecycle.ACTIVE,
            )

        return self.current_session

    def observation(
        self,
        *,
        present: bool,
        distance_to_robot: float | None = None,
    ) -> dict:
        """Build the small public observation without simulator identifiers."""
        if not isinstance(present, bool):
            raise ValueError("present must be a boolean.")

        output = {
            "session_id": self._session_id,
            "track_id": self._track.track_id,
            "present": present,
        }
        if present:
            if (
                isinstance(distance_to_robot, bool)
                or not isinstance(distance_to_robot, (int, float))
                or not math.isfinite(distance_to_robot)
                or distance_to_robot < 0.0
            ):
                raise ValueError(
                    "A present visitor requires a finite non-negative distance."
                )
            output["distance_to_robot"] = float(distance_to_robot)

        return output
