"""Deterministic synthetic data generation and local CSV/JSON persistence."""

from __future__ import annotations

import csv
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def generate_sensor_rows(seed: int = 17, count: int = 48) -> list[dict[str, Any]]:
    """Create reproducible simulated infrastructure sensor observations."""
    rng = random.Random(seed)
    rows = []
    start = datetime.now(timezone.utc) - timedelta(minutes=count)
    for index in range(count):
        rows.append(
            {
                "timestamp": (start + timedelta(minutes=index)).isoformat(),
                "power_kw": round(70 + 12 * rng.random() + (18 if index == 33 else 0), 2),
                "water_pressure_kpa": round(310 + 18 * rng.random() - (95 if index == 40 else 0), 2),
                "bridge_vibration": round(0.2 + 0.12 * rng.random() + (0.9 if index == 44 else 0), 3),
                "aqi": round(50 + 35 * rng.random() + (125 if index == 37 else 0), 1),
                "noise_db": round(42 + 15 * rng.random(), 1),
                "flood_level_m": round(0.05 + 0.18 * rng.random() + (0.72 if index == 46 else 0), 3),
            }
        )
    return rows


def generate_demo_events(seed: int = 17) -> list[dict[str, Any]]:
    """Create anonymized incident metadata for the dashboard and API."""
    rng = random.Random(seed)
    locations = ["Central Junction", "River Ward", "North Bridge", "Market Square"]
    events = []
    for index, (kind, severity) in enumerate(
        [("crowd_density", 0.83), ("environmental_threshold", 0.91),
         ("restricted_zone", 0.54), ("infrastructure_anomaly", 0.72)]
    ):
        events.append(
            {
                "id": f"incident-{index + 1}",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "kind": kind,
                "severity": severity,
                "location": locations[index],
                "description": f"Simulated {kind.replace('_', ' ')} signal",
                "metadata": {"source": f"edge-{rng.randint(1, 4)}", "identity_data": False},
            }
        )
    return events


def write_demo_data(directory: Path, seed: int = 17) -> tuple[Path, Path]:
    """Write generated sensor CSV and event JSON to a local directory."""
    directory.mkdir(parents=True, exist_ok=True)
    rows = generate_sensor_rows(seed)
    csv_path = directory / "sensor_readings.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    json_path = directory / "demo_events.json"
    json_path.write_text(json.dumps(generate_demo_events(seed), indent=2), encoding="utf-8")
    return csv_path, json_path
