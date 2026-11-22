"""Simulate local edge inference and parameter-only federated aggregation."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class EdgeNode:
    """Stateless camera-edge simulation that emits counts, never image payloads."""

    node_id: str
    confidence_threshold: float = 0.5

    def infer_metadata(self, detections: Sequence[dict[str, object]]) -> dict[str, object]:
        """Aggregate local detection labels into privacy-minimized metadata."""
        if not 0 <= self.confidence_threshold <= 1:
            raise ValueError("Confidence threshold must be between zero and one.")
        counts: dict[str, int] = {}
        for detection in detections:
            confidence = detection.get("confidence", 0.0)
            if not isinstance(confidence, (int, float)) or confidence < self.confidence_threshold:
                continue
            label = str(detection.get("label", "unknown"))
            counts[label] = counts.get(label, 0) + 1
        return {"node_id": self.node_id, "counts": counts, "raw_frame_included": False}


def fedavg(node_weights: Sequence[Sequence[float]], sample_counts: Sequence[int]) -> list[float]:
    """Compute sample-weighted FedAvg; only numeric model parameters are exchanged."""
    if not node_weights or len(node_weights) != len(sample_counts):
        raise ValueError("Weights and sample counts must have matching nonempty lengths.")
    if any(count <= 0 for count in sample_counts):
        raise ValueError("Sample counts must be positive.")
    width = len(node_weights[0])
    if any(len(weights) != width for weights in node_weights):
        raise ValueError("All model updates must have equal dimensions.")
    total = sum(sample_counts)
    return [
        sum(weights[index] * count for weights, count in zip(node_weights, sample_counts)) / total
        for index in range(width)
    ]


def compare_edge_cloud(
    frame_bytes: int = 500_000, metadata_bytes: int = 256, edge_latency_ms: float = 18.0,
    cloud_latency_ms: float = 140.0, frames: int = 60,
) -> dict[str, float]:
    """Compare one-minute uplink volume and nominal inference latency."""
    if min(frame_bytes, metadata_bytes, frames) < 0:
        raise ValueError("Byte sizes and frame count must be nonnegative.")
    return {
        "edge_latency_ms": edge_latency_ms,
        "cloud_latency_ms": cloud_latency_ms,
        "edge_uplink_bytes": float(metadata_bytes * frames),
        "cloud_uplink_bytes": float(frame_bytes * frames),
        "bandwidth_reduction_ratio": 1.0 - metadata_bytes / max(frame_bytes, 1),
    }
