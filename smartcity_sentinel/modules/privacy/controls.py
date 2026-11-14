"""Privacy utility functions with local-only storage semantics."""

from __future__ import annotations

import hashlib
import json
import math
import random
import time
from pathlib import Path
from typing import Any


def laplace_noisy_count(count: int, epsilon: float = 1.0, seed: int | None = None) -> float:
    """Add Laplace noise for a count query with unit sensitivity."""
    if count < 0 or epsilon <= 0:
        raise ValueError("Count must be nonnegative and epsilon must be positive.")
    rng = random.Random(seed)
    uniform = rng.random() - 0.5
    noise = -math.copysign(math.log1p(-2 * abs(uniform)), uniform) / epsilon
    return max(0.0, count + noise)


def minimize_event(event: dict[str, Any]) -> dict[str, Any]:
    """Keep only incident fields needed for aggregate operations."""
    allowed = ("id", "timestamp", "kind", "severity", "location", "description", "metadata")
    minimized = {key: event[key] for key in allowed if key in event}
    metadata = minimized.get("metadata")
    if isinstance(metadata, dict):
        minimized["metadata"] = {key: value for key, value in metadata.items() if key not in {"plate", "face", "name", "raw_frame"}}
    return minimized


def blur_regions(image: Any, regions: list[tuple[int, int, int, int]], kernel: int = 31) -> Any:
    """Blur supplied face/plate rectangles in an OpenCV image before persistence."""
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("Install opencv-python to blur image regions.") from error
    if kernel < 3:
        raise ValueError("Blur kernel must be at least 3.")
    kernel = kernel if kernel % 2 else kernel + 1
    height, width = image.shape[:2]
    output = image.copy()
    for x1, y1, x2, y2 in regions:
        x1, x2 = max(0, x1), min(width, x2)
        y1, y2 = max(0, y1), min(height, y2)
        if x1 < x2 and y1 < y2:
            output[y1:y2, x1:x2] = cv2.GaussianBlur(output[y1:y2, x1:x2], (kernel, kernel), 0)
    return output


def auto_blur_faces(image: Any, plate_regions: list[tuple[int, int, int, int]] | None = None) -> Any:
    """Detect faces with OpenCV's local Haar cascade and blur faces plus plate boxes."""
    try:
        import cv2
    except ImportError as error:
        raise RuntimeError("Install opencv-python to detect and blur faces.") from error
    cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
    detector = cv2.CascadeClassifier(str(cascade_path))
    if detector.empty():
        raise RuntimeError(f"Unable to load local face detector: {cascade_path}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    faces = detector.detectMultiScale(gray, scaleFactor=1.1, minNeighbors=5, minSize=(24, 24))
    regions = [
        (int(x), int(y), int(x + width), int(y + height))
        for x, y, width, height in faces
    ]
    regions.extend(plate_regions or [])
    return blur_regions(image, regions)


def purge_expired_files(directory: Path, retention_days: int, now: float | None = None) -> list[Path]:
    """Delete files older than the retention window; never recurse into subfolders."""
    if retention_days < 0:
        raise ValueError("Retention days cannot be negative.")
    cutoff = (time.time() if now is None else now) - retention_days * 86400
    deleted = []
    directory.mkdir(parents=True, exist_ok=True)
    for path in directory.iterdir():
        if path.is_file() and path.stat().st_mtime < cutoff:
            path.unlink()
            deleted.append(path)
    return deleted


class HashChainAuditLog:
    """Append-only JSON-lines audit log with SHA-256 hash chaining."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._previous_hash = self._last_hash()

    def _last_hash(self) -> str:
        if not self.path.exists():
            return "0" * 64
        last_line = ""
        with self.path.open(encoding="utf-8") as file:
            for line in file:
                if line.strip():
                    last_line = line
        if not last_line:
            return "0" * 64
        return str(json.loads(last_line)["hash"])

    def append(self, actor: str, action: str, details: dict[str, Any] | None = None) -> str:
        """Append one event and return its chain hash."""
        record = {"actor": actor, "action": action, "details": details or {}, "previous_hash": self._previous_hash}
        payload = json.dumps(record, sort_keys=True, separators=(",", ":"))
        digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
        with self.path.open("a", encoding="utf-8") as file:
            file.write(json.dumps({**record, "hash": digest}, sort_keys=True) + "\n")
        self._previous_hash = digest
        return digest

    def verify(self) -> bool:
        """Verify every entry and the predecessor link from the genesis hash."""
        previous = "0" * 64
        if not self.path.exists():
            return True
        with self.path.open(encoding="utf-8") as file:
            for line in file:
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                    digest = record.pop("hash")
                except (json.JSONDecodeError, KeyError, TypeError):
                    return False
                if not isinstance(record, dict):
                    return False
                if record.get("previous_hash") != previous:
                    return False
                payload = json.dumps(record, sort_keys=True, separators=(",", ":"))
                expected = hashlib.sha256(payload.encode("utf-8")).hexdigest()
                if digest != expected:
                    return False
                previous = digest
        return True


ROLE_PERMISSIONS = {
    "admin": frozenset({"read_alerts", "read_audit", "configure", "export_aggregates"}),
    "officer": frozenset({"read_alerts", "acknowledge_alerts"}),
    "public": frozenset({"read_public_aggregates"}),
}


def role_allows(role: str, permission: str) -> bool:
    """Check a role permission using a default-deny policy."""
    return permission in ROLE_PERMISSIONS.get(role, frozenset())
