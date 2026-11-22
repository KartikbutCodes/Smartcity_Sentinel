"""Validated local tools backed by the project's existing algorithms."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import random
import tempfile
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from smartcity_sentinel.modules.anomaly.detectors import (
    IsolationForestLite,
    TinyAutoencoder,
    remaining_useful_life,
)
from smartcity_sentinel.modules.crowd.density import density_grid, heatmap, stampede_risk
from smartcity_sentinel.modules.edge_sim.simulation import EdgeNode, compare_edge_cloud, fedavg
from smartcity_sentinel.modules.environment.monitor import forecast_arima_baseline
from smartcity_sentinel.modules.fairness.audit import bias_audit, explain_anomaly
from smartcity_sentinel.modules.operations import DEMO_CITY_GRAPH, prioritize_alert, shortest_route
from smartcity_sentinel.modules.privacy.controls import (
    HashChainAuditLog,
    ROLE_PERMISSIONS,
    laplace_noisy_count,
    minimize_event,
    role_allows,
)
from smartcity_sentinel.modules.traffic.analytics import (
    SignalQLearner,
    VirtualLineCounter,
    estimate_speed_mps,
    forecast_traffic_baseline,
    valid_indian_plate,
)
from smartcity_sentinel.modules.video_analytics.events import Detection, EventDetector

router = APIRouter(prefix="/tools", tags=["tools"])

SENSOR_FEATURES = ("power_kw", "water_pressure_kpa", "bridge_vibration")
_FORBIDDEN_PAYLOAD_KEYS = {"image", "images", "frame", "frames", "face_image", "raw_frame", "raw_image", "video"}


def build_anomaly_models() -> tuple[IsolationForestLite, TinyAutoencoder]:
    """Fit the two local scorers once from deterministic synthetic sensor rows."""
    from smartcity_sentinel.data.generate import generate_sensor_rows

    rows = generate_sensor_rows(seed=17)
    samples = [[row[name] for name in SENSOR_FEATURES] for row in rows[:30]]
    return IsolationForestLite().fit(samples), TinyAutoencoder().fit(samples)


def _object(value: Any, label: str = "Request body") -> dict[str, Any]:
    if not isinstance(value, dict):
        raise HTTPException(status_code=422, detail=f"{label} must be a JSON object.")
    return value


def _number(
    value: Any,
    label: str,
    *,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise HTTPException(status_code=422, detail=f"{label} must be a finite number.")
    try:
        result = float(value)
    except (OverflowError, ValueError) as error:
        raise HTTPException(status_code=422, detail=f"{label} must be a finite number.") from error
    if not math.isfinite(result):
        raise HTTPException(status_code=422, detail=f"{label} must be a finite number.")
    if minimum is not None and result < minimum:
        raise HTTPException(status_code=422, detail=f"{label} must be at least {minimum}.")
    if maximum is not None and result > maximum:
        raise HTTPException(status_code=422, detail=f"{label} must be at most {maximum}.")
    return result


def _integer(value: Any, label: str, *, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise HTTPException(status_code=422, detail=f"{label} must be an integer.")
    if not minimum <= value <= maximum:
        raise HTTPException(
            status_code=422,
            detail=f"{label} must be between {minimum} and {maximum}.",
        )
    return value


def _numbers(value: Any, label: str, *, maximum_length: int = 500) -> list[float]:
    if not isinstance(value, list) or not value:
        raise HTTPException(status_code=422, detail=f"{label} must be a non-empty array.")
    if len(value) > maximum_length:
        raise HTTPException(status_code=422, detail=f"{label} may contain at most {maximum_length} values.")
    return [_number(item, f"{label}[{index}]") for index, item in enumerate(value)]


def _point(value: Any, label: str) -> tuple[float, float]:
    values = _numbers(value, label, maximum_length=2)
    if len(values) != 2:
        raise HTTPException(status_code=422, detail=f"{label} must contain exactly two values.")
    return values[0], values[1]


def _reject_raw_payload(value: Any, path: str = "event") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold()
            if normalized in _FORBIDDEN_PAYLOAD_KEYS or "image" in normalized or "frame" in normalized or "video" in normalized:
                raise HTTPException(status_code=422, detail=f"{path}.{key} is not accepted.")
            _reject_raw_payload(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _reject_raw_payload(child, f"{path}[{index}]")


async def reject_raw_media(request: Request) -> None:
    if request.method == "POST":
        _reject_raw_payload(await request.json(), "request")


router.dependencies.append(Depends(reject_raw_media))


@router.get("/nodes")
def nodes() -> dict[str, Any]:
    """Return the built-in city graph used by the route planner."""
    return {"graph": DEMO_CITY_GRAPH, "nodes": list(DEMO_CITY_GRAPH)}


@router.post("/route")
def plan_route(payload: dict[str, Any]) -> dict[str, Any]:
    """Find the least-cost path between two nodes in the built-in city graph."""
    payload = _object(payload)
    start, destination = payload.get("start"), payload.get("destination")
    if not isinstance(start, str) or not isinstance(destination, str):
        raise HTTPException(status_code=422, detail="start and destination must be node names.")
    if start not in DEMO_CITY_GRAPH or destination not in DEMO_CITY_GRAPH:
        raise HTTPException(status_code=422, detail="start and destination must name known city nodes.")
    path, distance = shortest_route(DEMO_CITY_GRAPH, start, destination)
    return {"path": path, "distance": distance}


@router.post("/priority")
def alert_priority(payload: dict[str, Any]) -> dict[str, Any]:
    """Calculate an alert priority score from severity, impact, and confidence."""
    payload = _object(payload)
    result = prioritize_alert(
        _number(payload.get("severity"), "severity", minimum=0, maximum=1),
        _number(payload.get("impact", 0.5), "impact", minimum=0, maximum=1),
        _number(payload.get("confidence", 1.0), "confidence", minimum=0, maximum=1),
    )
    return {**result, "severity": float(payload["severity"])}


@router.post("/plate")
def check_plate(payload: dict[str, Any]) -> dict[str, Any]:
    """Check whether text matches a supported common Indian registration format."""
    payload = _object(payload)
    text = payload.get("text")
    if not isinstance(text, str) or not text.strip() or len(text) > 64:
        raise HTTPException(status_code=422, detail="text must be a non-empty plate string of at most 64 characters.")
    return {"text": text, "valid": valid_indian_plate(text)}


@router.post("/speed")
def speed_estimate(payload: dict[str, Any]) -> dict[str, float]:
    """Estimate speed from two image points and a supplied calibration matrix."""
    payload = _object(payload)
    first = _point(payload.get("first_point"), "first_point")
    second = _point(payload.get("second_point"), "second_point")
    elapsed = _number(payload.get("elapsed_seconds"), "elapsed_seconds", minimum=0)
    if elapsed == 0:
        raise HTTPException(status_code=422, detail="elapsed_seconds must be greater than zero.")
    matrix = payload.get("homography")
    if not isinstance(matrix, list) or len(matrix) != 3:
        raise HTTPException(status_code=422, detail="homography must be a 3 by 3 matrix.")
    matrix_values = [_numbers(row, f"homography[{index}]", maximum_length=3) for index, row in enumerate(matrix)]
    if any(len(row) != 3 for row in matrix_values):
        raise HTTPException(status_code=422, detail="homography must be a 3 by 3 matrix.")
    try:
        speed = estimate_speed_mps(first, second, elapsed, matrix_values)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"speed_mps": speed}


@router.post("/line-counter")
def line_counter(payload: dict[str, Any]) -> dict[str, Any]:
    """Count tracked positions that cross a horizontal image-space line."""
    payload = _object(payload)
    line_y = _number(payload.get("line_y"), "line_y")
    positions = payload.get("positions")
    if not isinstance(positions, list):
        raise HTTPException(status_code=422, detail="positions must be an array.")
    if len(positions) > 100:
        raise HTTPException(status_code=422, detail="positions may contain at most 100 records.")
    counter = VirtualLineCounter(line_y)
    crossings = []
    for index, position in enumerate(positions):
        if not isinstance(position, dict):
            raise HTTPException(status_code=422, detail=f"positions[{index}] must be an object.")
        track_id = _integer(position.get("track_id"), f"positions[{index}].track_id", minimum=0, maximum=1_000_000)
        center_y = _number(position.get("center_y"), f"positions[{index}].center_y")
        crossings.append({"track_id": track_id, "center_y": center_y, "crossed": counter.update(track_id, center_y)})
    return {"count": counter.count, "crossings": crossings}


@router.get("/crowd")
def crowd_heatmap() -> dict[str, Any]:
    """Return a heatmap and congestion score for seeded generated points."""
    rng = random.Random(17)
    points = [(rng.random(), rng.random()) for _ in range(60)]
    return _crowd_result(points)


def _crowd_result(points: list[tuple[float, float]]) -> dict[str, Any]:
    grid = density_grid(points)
    return {
        "points": points,
        "grid": grid,
        "heatmap": heatmap(grid),
        "crowd_risk": stampede_risk(grid),
    }


@router.post("/crowd")
def crowd_from_points(payload: dict[str, Any]) -> dict[str, Any]:
    """Measure density and congestion for at most 2,000 normalized points."""
    payload = _object(payload)
    raw_points = payload.get("points")
    if not isinstance(raw_points, list):
        raise HTTPException(status_code=422, detail="points must be an array.")
    if len(raw_points) > 2000:
        raise HTTPException(status_code=422, detail="points may contain at most 2,000 records.")
    points = []
    for index, value in enumerate(raw_points):
        point = _point(value, f"points[{index}]")
        if any(coordinate < 0 or coordinate > 1 for coordinate in point):
            raise HTTPException(status_code=422, detail=f"points[{index}] coordinates must be between 0 and 1.")
        points.append(point)
    return _crowd_result(points)


@router.post("/forecast")
def traffic_forecast(payload: dict[str, Any]) -> dict[str, Any]:
    """Return traffic and environmental trend-baseline forecasts for a number series."""
    payload = _object(payload)
    series = _numbers(payload.get("series"), "series")
    horizon = _integer(payload.get("horizon", 3), "horizon", minimum=1, maximum=100)
    return {
        "horizon": horizon,
        "traffic": {"label": "BASELINE", "values": forecast_traffic_baseline(series, horizon)},
        "environment": {"label": "BASELINE", "values": forecast_arima_baseline(series, horizon)},
    }


@router.post("/rul")
def remaining_life(payload: dict[str, Any]) -> dict[str, float | None]:
    """Estimate steps to a failure threshold using a simple degradation trend."""
    payload = _object(payload)
    degradation = _numbers(payload.get("degradation"), "degradation")
    threshold = _number(payload.get("failure_threshold"), "failure_threshold")
    rate = payload.get("current_rate")
    current_rate = None if rate is None else _number(rate, "current_rate")
    result = remaining_useful_life(degradation, threshold, current_rate)
    return {"remaining_useful_life": result if math.isfinite(result) else None}


@router.post("/anomaly")
def score_anomaly(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Score a three-feature sensor sample against locally fitted synthetic baselines."""
    payload = _object(payload)
    sample = _numbers(payload.get("sample"), "sample", maximum_length=len(SENSOR_FEATURES))
    if len(sample) != len(SENSOR_FEATURES):
        raise HTTPException(
            status_code=422,
            detail=f"sample must contain exactly {len(SENSOR_FEATURES)} sensor features.",
        )
    forest, autoencoder = request.app.state.anomaly_models
    feature_values = dict(zip(SENSOR_FEATURES, sample))
    baselines = dict(zip(SENSOR_FEATURES, autoencoder.mean))
    return {
        "isolation_score": forest.anomaly_score(sample),
        "reconstruction_error": autoencoder.reconstruction_error(sample),
        "deviations": explain_anomaly(feature_values, baselines),
    }


def _spot_anomaly_round(seed: int, request: Request) -> dict[str, Any]:
    from smartcity_sentinel.data.generate import generate_sensor_rows

    rows = generate_sensor_rows(seed=seed, count=48)
    source_indices = [2, 6, 12, 16, 24, 44]
    random.Random(seed).shuffle(source_indices)
    candidates = []
    forest, autoencoder = request.app.state.anomaly_models
    for source_index in source_indices:
        start = max(0, source_index - 3)
        end = min(len(rows), source_index + 4)
        candidates.append({
            "series": [row["bridge_vibration"] for row in rows[start:end]],
            "source_index": source_index,
            "sample": [rows[source_index][name] for name in SENSOR_FEATURES],
        })
    answer_index = next(index for index, candidate in enumerate(candidates) if candidate["source_index"] == 44)
    scores = [
        {
            "isolation_score": forest.anomaly_score(candidate["sample"]),
            "reconstruction_error": autoencoder.reconstruction_error(candidate["sample"]),
        }
        for candidate in candidates
    ]
    return {
        "series": [candidate["series"] for candidate in candidates],
        "answer_index": answer_index,
        "scores": scores,
    }


@router.get("/spot-anomaly")
def spot_anomaly(seed: int = 17) -> dict[str, Any]:
    """Create six seeded sensor sparklines without revealing the odd sample."""
    if isinstance(seed, bool) or not 0 <= seed <= 2**31 - 1:
        raise HTTPException(status_code=422, detail="seed must be between 0 and 2,147,483,647.")
    from smartcity_sentinel.data.generate import generate_sensor_rows

    rows = generate_sensor_rows(seed=seed, count=48)
    source_indices = [2, 6, 12, 16, 24, 44]
    random.Random(seed).shuffle(source_indices)
    return {
        "seed": seed,
        "feature": "bridge_vibration",
        "series": [
            [row["bridge_vibration"] for row in rows[max(0, index - 3):min(len(rows), index + 4)]]
            for index in source_indices
        ],
    }


@router.post("/spot-anomaly/score")
def score_spot_anomaly(payload: dict[str, Any], request: Request) -> dict[str, Any]:
    """Reveal both fitted-model scores after a six-sparkline guess."""
    payload = _object(payload)
    seed = _integer(payload.get("seed", 17), "seed", minimum=0, maximum=2**31 - 1)
    guess = _integer(payload.get("guess_index"), "guess_index", minimum=0, maximum=5)
    result = _spot_anomaly_round(seed, request)
    return {
        "guess_index": guess,
        "answer_index": result["answer_index"],
        "correct": guess == result["answer_index"],
        "scores": result["scores"],
        "models": ["IsolationForestLite", "TinyAutoencoder"],
    }


@router.post("/noisy-count")
def noisy_count(payload: dict[str, Any]) -> dict[str, Any]:
    """Generate seeded Laplace-noisy samples for an aggregate count and epsilon values."""
    payload = _object(payload)
    count = _integer(payload.get("count"), "count", minimum=0, maximum=1_000_000)
    epsilons = _numbers(payload.get("epsilons"), "epsilons", maximum_length=8)
    if any(not 0.05 <= epsilon <= 10 for epsilon in epsilons):
        raise HTTPException(status_code=422, detail="each epsilon must be between 0.05 and 10.")
    runs = [
        {
            "epsilon": epsilon,
            "samples": [laplace_noisy_count(count, epsilon=epsilon, seed=run) for run in range(50)],
        }
        for epsilon in epsilons
    ]
    return {"count": count, "runs_per_epsilon": 50, "runs": runs}


@router.post("/minimize")
def minimize_event_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Show an event before and after the project's field-minimization policy."""
    payload = _object(payload, "event")
    _reject_raw_payload(payload)
    if "metadata" in payload and not isinstance(payload["metadata"], dict):
        raise HTTPException(status_code=422, detail="metadata must be an object.")
    return {"before": payload, "after": minimize_event(payload)}


@router.get("/audit-chain")
def audit_chain() -> dict[str, Any]:
    """Create, tamper with, and verify a temporary sample hash-chained audit log."""
    with tempfile.TemporaryDirectory(prefix="smartcity-audit-") as directory:
        path = Path(directory) / "audit.jsonl"
        log = HashChainAuditLog(path)
        for block in range(1, 6):
            log.append("lab", f"block_{block}", {"sequence": block})
        valid_before = log.verify()
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        records[2]["details"]["sequence"] = "tampered"
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        valid_after = log.verify()
    return {
        "valid_before_tamper": valid_before,
        "valid_after_tamper": valid_after,
        "tampered_block": 3,
        "blocks": [
            {"number": index + 1, "hash": record["hash"], "previous_hash": record["previous_hash"]}
            for index, record in enumerate(records)
        ],
    }


@router.get("/audit-chain/sample")
def audit_chain_sample() -> dict[str, Any]:
    """Create five valid sample blocks in a temporary directory for the Lab."""
    with tempfile.TemporaryDirectory(prefix="smartcity-audit-") as directory:
        path = Path(directory) / "audit.jsonl"
        log = HashChainAuditLog(path)
        for block in range(1, 6):
            log.append("lab", f"block_{block}", {"sequence": block})
        valid = log.verify()
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    return {
        "valid": valid,
        "blocks": [
            {"number": index + 1, "hash": record["hash"], "previous_hash": record["previous_hash"], "valid": valid}
            for index, record in enumerate(records)
        ],
    }


@router.post("/audit-chain/tamper")
def tamper_audit_chain(payload: dict[str, Any]) -> dict[str, Any]:
    """Tamper with one temporary audit block and report the resulting chain break."""
    payload = _object(payload)
    block_number = _integer(payload.get("block_number"), "block_number", minimum=1, maximum=5)
    with tempfile.TemporaryDirectory(prefix="smartcity-audit-") as directory:
        path = Path(directory) / "audit.jsonl"
        log = HashChainAuditLog(path)
        for block in range(1, 6):
            log.append("lab", f"block_{block}", {"sequence": block})
        valid_before = log.verify()
        records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
        records[block_number - 1]["details"]["sequence"] = "tampered"
        path.write_text("".join(json.dumps(record) + "\n" for record in records), encoding="utf-8")
        valid_after = log.verify()

    broken = False
    previous = "0" * 64
    blocks = []
    for index, record in enumerate(records):
        block = dict(record)
        digest = block.pop("hash")
        expected = hashlib.sha256(
            json.dumps(block, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        broken = broken or block.get("previous_hash") != previous or digest != expected
        blocks.append({
            "number": index + 1,
            "hash": digest,
            "previous_hash": record["previous_hash"],
            "valid": not broken,
        })
        previous = digest
    return {
        "valid_before_tamper": valid_before,
        "valid_after_tamper": valid_after,
        "tampered_block": block_number,
        "blocks": blocks,
    }


@router.get("/roles")
def roles() -> dict[str, list[str]]:
    """List the example roles and their configured permission names."""
    return {role: sorted(permissions) for role, permissions in ROLE_PERMISSIONS.items()}


@router.get("/role-check")
def role_check(role: str, permission: str) -> dict[str, Any]:
    """Check one permission against the static example role map."""
    if role not in ROLE_PERMISSIONS:
        raise HTTPException(status_code=422, detail="role must be admin, officer, or public.")
    return {"role": role, "permission": permission, "allowed": role_allows(role, permission)}


@router.get("/bias")
def bias_report() -> dict[str, Any]:
    """Report per-group false-positive and false-negative rates for bundled sample data."""
    sample_path = Path(__file__).resolve().parents[2] / "data" / "sample_bias.csv"
    with sample_path.open(newline="", encoding="utf-8") as file:
        rows = [
            {
                "group": row["group"],
                "actual": row["actual"] == "1",
                "predicted": row["predicted"] == "1",
            }
            for row in csv.DictReader(file)
        ]
    result = bias_audit(rows)
    return {
        "groups": result,
        "warnings": [f"{group} has fewer than 30 samples." for group, values in result.items() if values["samples"] < 30],
    }


@router.post("/fedavg")
def federated_average(payload: dict[str, Any]) -> dict[str, Any]:
    """Compute a sample-count-weighted average of supplied numeric vectors."""
    payload = _object(payload)
    weights = payload.get("node_weights")
    counts = payload.get("sample_counts")
    if not isinstance(weights, list) or not weights or len(weights) > 100:
        raise HTTPException(status_code=422, detail="node_weights must contain 1 to 100 vectors.")
    if not isinstance(counts, list) or len(counts) != len(weights):
        raise HTTPException(status_code=422, detail="sample_counts must match node_weights.")
    normalized_weights = [_numbers(row, f"node_weights[{index}]") for index, row in enumerate(weights)]
    normalized_counts = [
        _integer(value, f"sample_counts[{index}]", minimum=1, maximum=1_000_000)
        for index, value in enumerate(counts)
    ]
    try:
        result = fedavg(normalized_weights, normalized_counts)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return {"weights": result}


@router.post("/edge")
def edge_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    """Count supplied detection labels that meet a confidence threshold."""
    payload = _object(payload)
    detections = payload.get("detections")
    if not isinstance(detections, list):
        raise HTTPException(status_code=422, detail="detections must be an array.")
    if len(detections) > 100:
        raise HTTPException(status_code=422, detail="detections may contain at most 100 records.")
    threshold = _number(payload.get("confidence_threshold", 0.5), "confidence_threshold", minimum=0, maximum=1)
    normalized = []
    for index, detection in enumerate(detections):
        if not isinstance(detection, dict) or not isinstance(detection.get("label"), str):
            raise HTTPException(status_code=422, detail=f"detections[{index}] needs a label string.")
        normalized.append({
            "label": detection["label"],
            "confidence": _number(detection.get("confidence", 0), f"detections[{index}].confidence", minimum=0, maximum=1),
        })
    return EdgeNode("lab-edge", threshold).infer_metadata(normalized)


@router.get("/edge-cloud")
def edge_cloud() -> dict[str, float]:
    """Return an illustrative edge-versus-cloud latency and data-volume comparison."""
    return compare_edge_cloud()


@router.post("/edge-cloud")
def edge_cloud_custom(payload: dict[str, Any]) -> dict[str, float]:
    """Compare configured frame and metadata volumes using the existing edge model."""
    payload = _object(payload)
    source_bytes = _integer(payload.get("source_bytes", 500_000), "source_bytes", minimum=1, maximum=10_000_000)
    metadata_bytes = _integer(payload.get("metadata_bytes", 256), "metadata_bytes", minimum=1, maximum=100_000)
    item_count = _integer(payload.get("item_count", 60), "item_count", minimum=1, maximum=2_000)
    edge_latency = _number(payload.get("edge_latency_ms", 18), "edge_latency_ms", minimum=0, maximum=10_000)
    cloud_latency = _number(payload.get("cloud_latency_ms", 140), "cloud_latency_ms", minimum=0, maximum=10_000)
    return compare_edge_cloud(source_bytes, metadata_bytes, edge_latency, cloud_latency, item_count)


def _evaluate_signal_policy(learner: SignalQLearner | None, seed: int) -> float:
    """Measure one fixed 30-step queue rollout for a trained or random policy."""
    environment = random.Random(seed)
    actions = random.Random(seed + 1)
    queues = [environment.randint(0, 12), environment.randint(0, 12)]
    reward = 0.0
    for step in range(30):
        state = (min(queues[0], 20), min(queues[1], 20), step % 4)
        action = learner.choose_action(state, explore=False, seed=seed + step) if learner else actions.randrange(2)
        queues[action] -= min(queues[action], environment.randint(2, 6))
        queues[0] += int(environment.random() < 0.35)
        queues[1] += int(environment.random() < 0.35)
        reward -= sum(queues)
    return reward


@router.post("/q-learning")
def q_learning(payload: dict[str, Any]) -> dict[str, Any]:
    """Train the toy traffic-signal learner and compare evaluation reward with random choices."""
    payload = _object(payload)
    episodes = _integer(payload.get("episodes", 50), "episodes", minimum=1, maximum=300)
    seed = _integer(payload.get("seed", 17), "seed", minimum=0, maximum=2**31 - 1)
    learner = SignalQLearner()
    reward_curve = []
    evaluation_seeds = [seed + 10_000 + offset for offset in range(3)]
    baseline_reward = round(
        sum(_evaluate_signal_policy(None, value) for value in evaluation_seeds) / len(evaluation_seeds), 2
    )
    random_baseline = [baseline_reward] * episodes
    for episode in range(episodes):
        learner.train(episodes=1, seed=seed + episode)
        reward_curve.append(round(sum(_evaluate_signal_policy(learner, value) for value in evaluation_seeds) / len(evaluation_seeds), 2))
    states = sorted(learner.q_values.items())
    return {
        "episodes": episodes,
        "state_count": len(states),
        "reward_curve": reward_curve,
        "random_baseline": random_baseline,
        "reward_label": "mean fixed-seed 30-step evaluation return after each training episode",
        "sample_q_values": [
            {"state": list(state), "actions": values}
            for state, values in states[:20]
        ],
    }


@router.post("/video-events")
def video_events(payload: dict[str, Any]) -> dict[str, Any]:
    """Run one scripted detection scenario through the event rules."""
    payload = _object(payload)
    scenario = payload.get("scenario")
    scenarios = {
        "loitering": [(250, 400, 0.0), (250, 400, 31.0)],
        "restricted_zone": [(800, 500, 0.0)],
        "sudden_motion": [(200, 400, 0.0), (400, 400, 1.0)],
        "abandoned_object": [(300, 400, 0.0), (302, 400, 50.0)],
    }
    if not isinstance(scenario, str) or scenario not in scenarios:
        raise HTTPException(status_code=422, detail="scenario must be loitering, restricted_zone, sudden_motion, or abandoned_object.")
    detector = EventDetector()
    frames = []
    events: list[dict[str, object]] = []
    for x, y, timestamp in scenarios[scenario]:
        detection = Detection("person" if scenario != "abandoned_object" else "object", 0.9, (x - 40, y - 40, x + 40, y + 40), track_id=1)
        events.extend(detector.update([detection], timestamp=timestamp, frame_size=(1000, 1000)))
        frames.append({"timestamp": timestamp, "box": list(detection.box), "label": detection.label})
    if scenario == "abandoned_object":
        event = detector.abandoned_object(1, 50.0, 2.0)
        if event is not None:
            events.append(event)
    return {"scenario": scenario, "frames": frames, "events": events}
