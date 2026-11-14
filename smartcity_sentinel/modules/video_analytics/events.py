"""Privacy-conscious tracking metadata and simple event rules."""

from __future__ import annotations

from dataclasses import dataclass, field
from math import hypot
from typing import Iterable


@dataclass(frozen=True)
class Detection:
    """A detector output; coordinates are frame pixels and contain no identity."""

    label: str
    confidence: float
    box: tuple[int, int, int, int]
    track_id: int | None = None

    @property
    def center(self) -> tuple[float, float]:
        """Return the center point of the bounding box."""
        x1, y1, x2, y2 = self.box
        return (x1 + x2) / 2, (y1 + y2) / 2


@dataclass
class TrackMemory:
    """Minimal per-track state for transient event detection."""

    first_seen: float
    last_seen: float
    positions: list[tuple[float, float]] = field(default_factory=list)


class EventDetector:
    """Detect duration, zone, and sudden-motion events from tracks."""

    def __init__(
        self,
        restricted_zone: tuple[float, float, float, float] = (0.7, 0.1, 0.98, 0.9),
        loitering_seconds: float = 30.0,
        sudden_motion_pixels: float = 110.0,
    ) -> None:
        self.restricted_zone = restricted_zone
        self.loitering_seconds = loitering_seconds
        self.sudden_motion_pixels = sudden_motion_pixels
        self._tracks: dict[int, TrackMemory] = {}

    def update(
        self,
        detections: Iterable[Detection],
        timestamp: float,
        frame_size: tuple[int, int] = (1, 1),
    ) -> list[dict[str, object]]:
        """Return event metadata for detections in normalized frame coordinates."""
        frame_width, frame_height = frame_size
        if frame_width <= 0 or frame_height <= 0:
            raise ValueError("Frame dimensions must be positive.")
        events: list[dict[str, object]] = []
        x_min, y_min, x_max, y_max = self.restricted_zone
        for detection in detections:
            if detection.track_id is None:
                continue
            center_x, center_y = detection.center
            x, y = center_x / frame_width, center_y / frame_height
            point = (x, y)
            memory = self._tracks.setdefault(
                detection.track_id, TrackMemory(timestamp, timestamp)
            )
            previous = memory.positions[-1] if memory.positions else None
            memory.positions.append(point)
            memory.positions = memory.positions[-10:]
            memory.last_seen = timestamp
            if previous is not None and hypot(
                (x - previous[0]) * frame_width, (y - previous[1]) * frame_height
            ) >= self.sudden_motion_pixels:
                events.append({"kind": "sudden_motion", "track_id": detection.track_id})
            if timestamp - memory.first_seen >= self.loitering_seconds:
                events.append({"kind": "loitering", "track_id": detection.track_id})
            if x_min <= x <= x_max and y_min <= y <= y_max:
                events.append({"kind": "restricted_zone_intrusion", "track_id": detection.track_id})
        return events

    def expire(self, timestamp: float, max_idle_seconds: float = 10.0) -> None:
        """Forget tracks that have not appeared recently."""
        self._tracks = {
            track_id: state
            for track_id, state in self._tracks.items()
            if timestamp - state.last_seen <= max_idle_seconds
        }

    @staticmethod
    def abandoned_object(
        object_track_id: int,
        duration_seconds: float,
        stationary_displacement: float,
        minimum_seconds: float = 45.0,
        max_displacement: float = 5.0,
    ) -> dict[str, object] | None:
        """Flag a stationary object persisting beyond a configurable duration."""
        if duration_seconds >= minimum_seconds and stationary_displacement <= max_displacement:
            return {"kind": "abandoned_object", "object_track_id": object_track_id}
        return None


def sudden_motion_from_flow(flow_vectors: Iterable[tuple[float, float]], threshold: float = 8.0) -> bool:
    """Detect a coarse motion spike from supplied optical-flow vectors."""
    magnitudes = [hypot(dx, dy) for dx, dy in flow_vectors]
    return bool(magnitudes and sum(magnitudes) / len(magnitudes) >= threshold)


def calculate_optical_flow(
    previous_frame: object, current_frame: object, grid_size: int = 8
) -> list[tuple[float, float]]:
    """Compute sparse grid samples from dense OpenCV Farneback optical flow."""
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("Install opencv-python to calculate optical flow.") from error
    if grid_size < 1:
        raise ValueError("Grid size must be positive.")
    previous_gray = cv2.cvtColor(previous_frame, cv2.COLOR_BGR2GRAY)
    current_gray = cv2.cvtColor(current_frame, cv2.COLOR_BGR2GRAY)
    flow = cv2.calcOpticalFlowFarneback(previous_gray, current_gray, None, 0.5, 3, 15, 3, 5, 1.2, 0)
    height, width = flow.shape[:2]
    return [
        (float(flow[y, x, 0]), float(flow[y, x, 1]))
        for y in range(grid_size // 2, height, grid_size)
        for x in range(grid_size // 2, width, grid_size)
    ]
