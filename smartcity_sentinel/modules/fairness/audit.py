"""Group-level binary-classifier error rates for offline fairness checks."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
import csv
import json
from pathlib import Path
from typing import Any


def bias_audit(rows: Iterable[dict[str, Any]]) -> dict[str, dict[str, float | int]]:
    """Report per-group false-positive and false-negative rates."""
    grouped: dict[str, list[int]] = defaultdict(lambda: [0, 0, 0, 0])
    for row in rows:
        group = str(row["group"])
        actual, predicted = bool(row["actual"]), bool(row["predicted"])
        counts = grouped[group]
        if actual and predicted:
            counts[0] += 1
        elif actual:
            counts[1] += 1
        elif predicted:
            counts[2] += 1
        else:
            counts[3] += 1
    return {
        group: {
            "false_positive_rate": fp / (fp + tn) if fp + tn else 0.0,
            "false_negative_rate": fn / (fn + tp) if fn + tp else 0.0,
            "samples": sum(counts),
        }
        for group, (tp, fn, fp, tn) in grouped.items()
    }


def explain_anomaly(features: dict[str, float], baselines: dict[str, float]) -> dict[str, float]:
    """Return absolute per-feature deviations as a transparent explanation baseline."""
    return {
        feature: abs(value - baselines.get(feature, value))
        for feature, value in features.items()
    }


def main() -> None:
    """Run the included sample per-group error-rate audit."""
    sample_path = Path(__file__).resolve().parents[3] / "data" / "sample_bias.csv"
    with sample_path.open(newline="", encoding="utf-8") as file:
        rows = [
            {"group": row["group"], "actual": row["actual"] == "1", "predicted": row["predicted"] == "1"}
            for row in csv.DictReader(file)
        ]
    print(json.dumps(bias_audit(rows), indent=2))


if __name__ == "__main__":
    main()
