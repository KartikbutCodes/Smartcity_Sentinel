"""Read-only seeded example responses for the Examples page."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from smartcity_sentinel.data.generate import generate_sensor_rows
from smartcity_sentinel.modules.anomaly.detectors import IsolationForestLite
from smartcity_sentinel.modules.edge_sim.simulation import EdgeNode, compare_edge_cloud
from smartcity_sentinel.modules.environment.monitor import threshold_alerts
from smartcity_sentinel.modules.privacy.controls import minimize_event
from smartcity_sentinel.modules.traffic.analytics import (
    VirtualLineCounter,
    estimate_speed_mps,
    valid_indian_plate,
)

router = APIRouter(prefix="/examples", tags=["examples"])
FEATURES = ("power_kw", "water_pressure_kpa", "bridge_vibration")


def _seed(value: int) -> int:
    if value < 0 or value > 2_147_483_647:
        raise HTTPException(status_code=422, detail="seed must be between 0 and 2147483647.")
    return value


@router.get("/sensors")
def sensor_examples(seed: int = Query(17, ge=0, le=2_147_483_647)) -> dict[str, Any]:
    """Return 48 seeded sensor rows and scores from the compact isolation model."""
    seed = _seed(seed)
    rows = generate_sensor_rows(seed=seed, count=48)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for index, row in enumerate(rows):
        row["timestamp"] = (start + timedelta(minutes=index)).isoformat()

    forest = IsolationForestLite(seed=seed).fit([
        [row[name] for name in FEATURES] for row in rows[:30]
    ])
    scored = []
    for index, row in enumerate(rows):
        unusual_score = round(forest.anomaly_score([row[name] for name in FEATURES]), 6)
        scored.append({**row, "unusual_score": unusual_score, "index": index})

    highest = sorted(scored, key=lambda row: row["unusual_score"], reverse=True)[:3]
    latest = rows[-1]
    return {
        "seed": seed,
        "rows": scored,
        "highest_indexes": [row["index"] for row in highest],
        "threshold_alerts": threshold_alerts(latest),
        "latest": latest,
        "method": "IsolationForestLite",
        "method_plain": "A small check that marks readings that differ from the sample.",
    }


@router.get("/traffic-camera")
def traffic_camera_examples(seed: int = Query(17, ge=0, le=2_147_483_647)) -> dict[str, Any]:
    """Return a deterministic 30-second drawn-camera scene and its summaries."""
    seed = _seed(seed)
    rng = random.Random(seed)
    frame_count = 150
    vehicles = []
    for index in range(12):
        lane_index = index % 4
        lane = (0.28, 0.38, 0.58, 0.68)[lane_index]
        direction = 1 if lane_index < 2 else -1
        slot = index // 4
        start_x = (0.12 + slot * 0.30) if direction == 1 else (0.88 - slot * 0.30)
        speed = 0.004
        vehicles.append({
            "track_id": 100 + index,
            "label": "bike" if index in (3, 8) else "car",
            "direction": direction,
            "lane": lane,
            "start_x": start_x,
            "speed": speed,
            "confidence": round(0.82 + rng.random() * 0.15, 3),
        })
    people = []
    for index in range(3):
        direction = 1 if index != 1 else -1
        start_x = (0.20, 0.50, 0.80)[index]
        people.append({
            "track_id": 200 + index,
            "label": "person",
            "direction": direction,
            "lane": 0.49,
            "start_x": start_x,
            "speed": 0.0015,
            "confidence": round(0.78 + rng.random() * 0.16, 3),
        })

    scale_homography = [[10.0, 0.0, 0.0], [0.0, 10.0, 0.0], [0.0, 0.0, 1.0]]
    frames = []
    crossings = []
    counter = VirtualLineCounter(0.5)
    previous_positions: dict[int, tuple[float, float]] = {}
    speeds: list[dict[str, Any]] = []
    vehicle_speeds: dict[int, list[float]] = {}
    bins = [0] * 6

    for frame in range(frame_count):
        second = frame / 5
        detections = []
        for item in vehicles + people:
            offset = item["speed"] * frame * item["direction"]
            x = item["start_x"] + offset
            x = 0.05 + ((x - 0.05) % 0.90)
            y = item["lane"]
            width = 0.13 if item["label"] != "person" else 0.035
            height = 0.08 if item["label"] == "car" else (0.12 if item["label"] == "bike" else 0.12)
            box = [round(x - width / 2, 4), round(y - height / 2, 4),
                   round(x + width / 2, 4), round(y + height / 2, 4)]
            detections.append({
                "track_id": item["track_id"],
                "label": item["label"],
                "confidence": item["confidence"],
                "box": box,
            })
            if item["label"] != "person":
                center_y = 0.50 + 0.22 * (1 if frame % 30 < 15 else -1)
                crossed = counter.update(item["track_id"], center_y)
                if crossed:
                    crossings.append({
                        "track_id": item["track_id"],
                        "frame": frame,
                        "second": round(second, 1),
                    })
                old = previous_positions.get(item["track_id"])
                current = (x, y)
                if old is not None:
                    mps = estimate_speed_mps(old, current, 0.2, scale_homography)
                    vehicle_speeds.setdefault(item["track_id"], []).append(mps)
                previous_positions[item["track_id"]] = current
        edge = EdgeNode("example-camera", 0.5)
        metadata = edge.infer_metadata(detections)
        frames.append({
            "frame": frame,
            "second": round(second, 1),
            "detections": detections,
            "metadata": metadata,
        })
        if frame % 5 == 0:
            bins[min(5, int(second // 5))] += sum(
                1 for detection in detections if detection["label"] != "person"
            )

    speeds = []
    for track_id, values in vehicle_speeds.items():
        if values:
            average_mps = sum(values) / len(values)
            speeds.append({
                "track_id": track_id,
                "speed_kmh": round(average_mps * 3.6, 2),
            })

    per_second = [
        {
            "second": index,
            "counts": EdgeNode("example-camera", 0.5).infer_metadata(
                frames[index * 5]["detections"]
            )["counts"],
            "raw_frame_included": False,
        }
        for index in range(30)
    ]
    comparison = compare_edge_cloud(
        frame_bytes=500_000,
        metadata_bytes=256,
        edge_latency_ms=18.0,
        cloud_latency_ms=140.0,
        frames=150,
    )
    return {
        "seed": seed,
        "duration_seconds": 30,
        "fps": 5,
        "frames": frames,
        "crossings": crossings,
        "speeds": speeds,
        "speed_scale": "A scale homography maps normalized image points. It is a made-up scale.",
        "homography": scale_homography,
        "per_second_metadata": per_second,
        "vehicles_per_5_seconds": bins,
        "edge_cloud": comparison,
    }


@router.get("/plate-camera")
def plate_camera_examples(seed: int = Query(17, ge=0, le=2_147_483_647)) -> dict[str, Any]:
    """Return 12 seeded plate reads and exact privacy minimizer inputs and outputs."""
    seed = _seed(seed)
    rng = random.Random(seed)
    states = ("KA", "MH", "DL", "TN")
    reads = []
    hourly = [0] * 12
    for index in range(12):
        state = states[index % len(states)]
        if index in (4, 9):
            text = f"{state} 0{rng.choice(('X', 'Q'))} X1 {rng.randint(100, 999)}"
            valid = valid_indian_plate(text)
        else:
            text = f"{state} {rng.randint(10, 99)} {chr(65 + rng.randint(0, 25))}{chr(65 + rng.randint(0, 25))} {rng.randint(1000, 9999)}"
            valid = valid_indian_plate(text)
        hour = 8 + index // 4
        hourly[hour - 8] += 1
        minute = 3 + rng.randint(0, 12)
        timestamp = f"2026-01-01T{hour:02d}:{minute:02d}:00+00:00"
        confidence = round(rng.uniform(0.72, 0.99), 3)
        before = {
            "id": f"plate-read-{index + 1}",
            "timestamp": timestamp,
            "kind": "plate_read",
            "severity": confidence,
            "location": "Plate reader camera",
            "description": "Random plate-read example",
            "metadata": {
                "plate": text,
                "camera_id": "plate-reader-camera-1",
                "face": "not-used",
                "name": "not-used",
                "raw_frame": "not-included",
                "confidence": confidence,
            },
        }
        after = minimize_event(before)
        reads.append({
            "id": before["id"],
            "time": timestamp,
            "plate_text": text,
            "confidence": confidence,
            "camera_id": "plate-reader-camera-1",
            "valid": valid,
            "misread_explanation": (
                "The camera misread one character, so the format check fails."
                if not valid else ""
            ),
            "before": before,
            "after": after,
        })
    return {
        "seed": seed,
        "camera_name": "plate-reader camera (ALPR)",
        "reads": reads,
        "reads_per_hour": [
            {"hour": f"{8 + index:02d}:00", "count": count}
            for index, count in enumerate(hourly)
        ],
    }
