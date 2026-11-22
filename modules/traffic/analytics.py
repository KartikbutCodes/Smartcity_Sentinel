"""Dependency-free traffic analytics baselines and optional OCR adapter."""

from __future__ import annotations

import re
from collections import defaultdict
from typing import Any, Sequence


INDIAN_PLATE_PATTERN = re.compile(
    r"^(?:[A-Z]{2}\s?\d{1,2}\s?(?:[A-Z]{1,3}\s?)?\d{1,4}|"
    r"BH\s?\d{2}\s?[A-Z]{2}\s?\d{4})$"
)


def valid_indian_plate(text: str) -> bool:
    """Validate common Indian registration-number formats after cleanup."""
    normalized = re.sub(r"[^A-Z0-9 ]", "", text.upper()).strip()
    return bool(INDIAN_PLATE_PATTERN.fullmatch(normalized))


class VirtualLineCounter:
    """Count track crossings of a horizontal image-space line."""

    def __init__(self, y: float) -> None:
        self.y = y
        self._last_side: dict[int, int] = {}
        self.count = 0

    def update(self, track_id: int, center_y: float) -> bool:
        """Update a track position and return True exactly once per crossing."""
        side = 1 if center_y >= self.y else -1
        previous = self._last_side.get(track_id)
        self._last_side[track_id] = side
        if previous is not None and previous != side:
            self.count += 1
            return True
        return False


def project_homography(
    point: tuple[float, float], matrix: Sequence[Sequence[float]]
) -> tuple[float, float]:
    """Project an image point through a 3x3 homography matrix."""
    if len(matrix) != 3 or any(len(row) != 3 for row in matrix):
        raise ValueError("Homography must be a 3x3 matrix.")
    x, y = point
    denominator = matrix[2][0] * x + matrix[2][1] * y + matrix[2][2]
    if denominator == 0:
        raise ValueError("Homography maps this point to infinity.")
    return (
        (matrix[0][0] * x + matrix[0][1] * y + matrix[0][2]) / denominator,
        (matrix[1][0] * x + matrix[1][1] * y + matrix[1][2]) / denominator,
    )


def estimate_speed_mps(
    first_point: tuple[float, float],
    second_point: tuple[float, float],
    elapsed_seconds: float,
    homography: Sequence[Sequence[float]],
) -> float:
    """Estimate speed using world-coordinate points from a calibrated homography."""
    if elapsed_seconds <= 0:
        raise ValueError("Elapsed time must be positive.")
    p1 = project_homography(first_point, homography)
    p2 = project_homography(second_point, homography)
    return ((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) ** 0.5 / elapsed_seconds


def forecast_traffic_baseline(
    series: Sequence[float], horizon: int = 1, lookback: int = 8
) -> list[float]:
    """Return a dependency-free recurrent baseline for synthetic traffic series.

    This is a lightweight trend heuristic, not a trained neural network.
    """
    if horizon < 1:
        raise ValueError("Horizon must be at least one.")
    if not series:
        raise ValueError("At least one traffic observation is required.")
    window = list(series[-lookback:])
    values = []
    for _ in range(horizon):
        delta = (window[-1] - window[0]) / max(len(window) - 1, 1)
        next_value = max(0.0, window[-1] + delta * 0.35)
        values.append(next_value)
        window = (window + [next_value])[-lookback:]
    return values


class SignalQLearner:
    """Tabular Q-learning controller for a two-road SUMO-like toy junction."""

    def __init__(self, alpha: float = 0.2, gamma: float = 0.9, epsilon: float = 0.15) -> None:
        self.alpha, self.gamma, self.epsilon = alpha, gamma, epsilon
        self.q_values: dict[tuple[int, int, int], list[float]] = defaultdict(lambda: [0.0, 0.0])

    def choose_action(self, state: tuple[int, int, int], explore: bool = True, seed: int = 17) -> int:
        """Select phase 0 or 1 using epsilon-greedy selection."""
        import random
        rng = random.Random(seed + sum(state))
        if explore and rng.random() < self.epsilon:
            return rng.randrange(2)
        return max(range(2), key=lambda action: self.q_values[state][action])

    def update(
        self,
        state: tuple[int, int, int],
        action: int,
        reward: float,
        next_state: tuple[int, int, int],
    ) -> None:
        """Apply one tabular Q-learning update."""
        old = self.q_values[state][action]
        future = max(self.q_values[next_state])
        self.q_values[state][action] = old + self.alpha * (reward + self.gamma * future - old)

    def train(self, episodes: int = 300, seed: int = 17) -> None:
        """Train against a local stochastic queue simulation."""
        import random
        rng = random.Random(seed)
        for _ in range(episodes):
            queues = [rng.randint(0, 12), rng.randint(0, 12)]
            for _step in range(30):
                state = (min(queues[0], 20), min(queues[1], 20), _step % 4)
                action = self.choose_action(state, seed=rng.randint(0, 10**6))
                served = min(queues[action], rng.randint(2, 6))
                queues[action] -= served
                queues[0] += int(rng.random() < 0.35)
                queues[1] += int(rng.random() < 0.35)
                next_state = (min(queues[0], 20), min(queues[1], 20), (_step + 1) % 4)
                self.update(state, action, -sum(queues), next_state)


def read_plate_with_ocr(image: object, reader: object) -> list[str]:
    """Run an injected EasyOCR-compatible reader and retain only valid plate text."""
    readtext = getattr(reader, "readtext", None)
    if readtext is None:
        raise TypeError("reader must provide a readtext(image) method.")
    return [str(result[1]).upper() for result in readtext(image) if len(result) > 1 and valid_indian_plate(str(result[1]))]


def create_offline_easyocr_reader(model_directory: str) -> object:
    """Create an EasyOCR reader without network downloads from local model files."""
    try:
        import easyocr
    except ImportError as error:
        raise RuntimeError("Install the optional 'easyocr' package for plate OCR.") from error
    return easyocr.Reader(
        ["en"], gpu=False, model_storage_directory=model_directory, download_enabled=False
    )
