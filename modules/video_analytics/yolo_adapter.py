"""Optional local YOLO/ByteTrack adapter; models must already exist on disk."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from .events import Detection


class LocalYoloTracker:
    """Run a local Ultralytics detector and ByteTrack without downloading weights."""

    def __init__(self, model_path: str, confidence: float = 0.35) -> None:
        if not Path(model_path).is_file():
            raise FileNotFoundError("YOLO weights must be an existing local model file.")
        try:
            from ultralytics import YOLO
        except ImportError as error:
            raise RuntimeError("Install the optional 'ultralytics' package to use YOLO.") from error
        self._model: Any = YOLO(model_path)
        self.confidence = confidence

    def process_frame(self, frame: Any) -> list[Detection]:
        """Detect and track objects in one OpenCV frame."""
        results = self._model.track(
            frame, persist=True, tracker="bytetrack.yaml", conf=self.confidence, verbose=False
        )
        detections: list[Detection] = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for index in range(len(boxes)):
                coordinates = tuple(int(value) for value in boxes.xyxy[index].tolist())
                track_id = None if boxes.id is None else int(boxes.id[index].item())
                detections.append(
                    Detection(
                        label=result.names[int(boxes.cls[index].item())],
                        confidence=float(boxes.conf[index].item()),
                        box=coordinates,  # type: ignore[arg-type]
                        track_id=track_id,
                    )
                )
        return detections

    def run_video(
        self,
        source: str | int,
        on_frame: Callable[[Any, list[Detection]], None],
        max_frames: int | None = None,
    ) -> int:
        """Process a local video or webcam and release the capture without saving frames."""
        try:
            import cv2
        except ImportError as error:
            raise RuntimeError("Install opencv-python to read video or camera frames.") from error
        capture = cv2.VideoCapture(source)
        if not capture.isOpened():
            capture.release()
            raise RuntimeError(f"Unable to open video source: {source!r}")
        processed = 0
        try:
            while max_frames is None or processed < max_frames:
                success, frame = capture.read()
                if not success:
                    break
                on_frame(frame, self.process_frame(frame))
                processed += 1
        finally:
            capture.release()
        return processed
