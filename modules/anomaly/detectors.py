"""Small dependency-free anomaly baselines suitable for synthetic streams."""

from __future__ import annotations

import math
import random
from collections.abc import Sequence


class IsolationForestLite:
    """A compact isolation-tree ensemble implementing randomized partitions."""

    def __init__(self, trees: int = 40, sample_size: int = 32, seed: int = 17) -> None:
        self.trees, self.sample_size, self.seed = trees, sample_size, seed
        self._forest: list[object] = []
        self._dimensions = 0

    def fit(self, samples: Sequence[Sequence[float]]) -> "IsolationForestLite":
        """Fit isolation trees to numeric feature vectors."""
        if not samples or not samples[0]:
            raise ValueError("Training data cannot be empty.")
        if any(len(sample) != len(samples[0]) for sample in samples):
            raise ValueError("All feature vectors must have equal length.")
        self._dimensions = len(samples[0])
        max_depth = max(1, math.ceil(math.log2(max(2, self.sample_size))))
        rng = random.Random(self.seed)

        def grow(data: list[tuple[float, ...]], depth: int) -> object:
            if depth >= max_depth or len(data) < 2:
                return ("leaf", len(data))
            viable = [index for index in range(self._dimensions) if min(row[index] for row in data) < max(row[index] for row in data)]
            if not viable:
                return ("leaf", len(data))
            feature = rng.choice(viable)
            low, high = min(row[feature] for row in data), max(row[feature] for row in data)
            split = rng.uniform(low, high)
            left = [row for row in data if row[feature] < split]
            right = [row for row in data if row[feature] >= split]
            if not left or not right:
                return ("leaf", len(data))
            return ("node", feature, split, grow(left, depth + 1), grow(right, depth + 1))

        self._forest = []
        for _ in range(self.trees):
            sample = [tuple(row) for row in rng.sample(list(samples), min(len(samples), self.sample_size))]
            self._forest.append(grow(sample, 0))
        return self

    def anomaly_score(self, sample: Sequence[float]) -> float:
        """Return a [0, 1] anomaly score; higher means easier to isolate."""
        if not self._forest or len(sample) != self._dimensions:
            raise ValueError("Fit the model and provide a matching feature vector.")

        def path(node: object, row: Sequence[float], depth: int = 0) -> float:
            if node[0] == "leaf":  # type: ignore[index]
                size = node[1]  # type: ignore[index]
                return depth + (0 if size <= 1 else 2 * math.log(size) + 0.577)
            _, feature, split, left, right = node  # type: ignore[misc]
            return path(left if row[feature] < split else right, row, depth + 1)

        average = sum(path(tree, sample) for tree in self._forest) / len(self._forest)
        normalizer = 2 * math.log(max(2, self.sample_size)) + 0.577
        return 2 ** (-average / normalizer)


class TinyAutoencoder:
    """Train a compact one-hidden-layer tanh autoencoder using pure Python."""

    def __init__(self, hidden_size: int | None = None, seed: int = 17) -> None:
        self.hidden_size = hidden_size
        self.seed = seed
        self.mean: list[float] = []
        self.scale: list[float] = []
        self._encoder: list[list[float]] = []
        self._decoder: list[list[float]] = []
        self._hidden_bias: list[float] = []
        self._output_bias: list[float] = []

    def fit(
        self, samples: Sequence[Sequence[float]], epochs: int = 120, learning_rate: float = 0.015
    ) -> "TinyAutoencoder":
        """Train a small autoencoder with stochastic gradient descent."""
        if not samples or not samples[0]:
            raise ValueError("Training data cannot be empty.")
        if epochs < 1 or learning_rate <= 0:
            raise ValueError("Epochs and learning rate must be positive.")
        if any(len(row) != len(samples[0]) for row in samples):
            raise ValueError("All feature vectors must have equal length.")
        rng = random.Random(self.seed)
        self.mean = [sum(row[i] for row in samples) / len(samples) for i in range(len(samples[0]))]
        self.scale = [
            max(1e-6, math.sqrt(sum((row[i] - self.mean[i]) ** 2 for row in samples) / len(samples)))
            for i in range(len(self.mean))
        ]
        width = len(self.mean)
        hidden = self.hidden_size or max(1, width // 2)
        if hidden < 1:
            raise ValueError("Hidden size must be positive.")
        self._encoder = [[rng.uniform(-0.15, 0.15) for _ in range(hidden)] for _ in range(width)]
        self._decoder = [[rng.uniform(-0.15, 0.15) for _ in range(width)] for _ in range(hidden)]
        self._hidden_bias = [0.0] * hidden
        self._output_bias = [0.0] * width
        normalized = [
            [(value - self.mean[index]) / self.scale[index] for index, value in enumerate(row)]
            for row in samples
        ]
        for _ in range(epochs):
            for vector in normalized:
                hidden_values = [
                    math.tanh(self._hidden_bias[j] + sum(vector[i] * self._encoder[i][j] for i in range(width)))
                    for j in range(hidden)
                ]
                reconstruction = [
                    self._output_bias[i] + sum(hidden_values[j] * self._decoder[j][i] for j in range(hidden))
                    for i in range(width)
                ]
                output_gradient = [2 * (reconstruction[i] - vector[i]) / width for i in range(width)]
                hidden_gradient = [
                    sum(output_gradient[i] * self._decoder[j][i] for i in range(width))
                    * (1 - hidden_values[j] ** 2)
                    for j in range(hidden)
                ]
                for j in range(hidden):
                    for i in range(width):
                        self._decoder[j][i] -= learning_rate * output_gradient[i] * hidden_values[j]
                    self._hidden_bias[j] -= learning_rate * hidden_gradient[j]
                for i in range(width):
                    for j in range(hidden):
                        self._encoder[i][j] -= learning_rate * hidden_gradient[j] * vector[i]
                    self._output_bias[i] -= learning_rate * output_gradient[i]
        return self

    def reconstruction_error(self, sample: Sequence[float]) -> float:
        """Return normalized reconstruction error for an observation."""
        if not self.mean or len(sample) != len(self.mean):
            raise ValueError("Fit the model and provide a matching feature vector.")
        vector = [(value - self.mean[i]) / self.scale[i] for i, value in enumerate(sample)]
        hidden = [
            math.tanh(self._hidden_bias[j] + sum(vector[i] * self._encoder[i][j] for i in range(len(vector))))
            for j in range(len(self._hidden_bias))
        ]
        reconstructed = [
            self._output_bias[i] + sum(hidden[j] * self._decoder[j][i] for j in range(len(hidden)))
            for i in range(len(vector))
        ]
        return sum((value - reconstructed[i]) ** 2 for i, value in enumerate(vector)) / len(vector)


def remaining_useful_life(
    degradation: Sequence[float], failure_threshold: float, current_rate: float | None = None
) -> float:
    """Estimate steps to failure from a simple recent-trend extrapolation."""
    if not degradation:
        raise ValueError("At least one degradation reading is required.")
    if current_rate is None:
        current_rate = (degradation[-1] - degradation[0]) / max(1, len(degradation) - 1)
    if current_rate <= 0:
        return math.inf
    return max(0.0, (failure_threshold - degradation[-1]) / current_rate)
