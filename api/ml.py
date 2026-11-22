"""Dependency-free heuristic baseline endpoints for the local dashboard."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from smartcity_sentinel.data.generate import generate_sensor_rows
from smartcity_sentinel.modules.anomaly.detectors import IsolationForestLite, TinyAutoencoder
from smartcity_sentinel.modules.traffic.analytics import forecast_traffic_baseline

router = APIRouter(prefix="/ml", tags=["baselines"])
FEATURES = ("power_kw", "water_pressure_kpa", "bridge_vibration", "aqi", "noise_db", "flood_level_m")

def _fitted_baselines():
    rows = generate_sensor_rows(seed=17)
    samples = [[float(row[key]) for key in FEATURES] for row in rows[:30]]
    return rows, IsolationForestLite().fit(samples), TinyAutoencoder().fit(samples)

@router.get("/status")
async def ml_status() -> dict[str, object]:
    return {"status": "baseline", "models_trained": False,
            "methods": ["traffic trend heuristic", "IsolationForestLite", "pure-Python TinyAutoencoder"],
            "message": "These are dependency-free demonstrations; no neural network is trained."}

@router.get("/traffic")
async def ml_traffic() -> dict[str, object]:
    return {"status": "baseline", "method": "traffic trend heuristic",
            "forecast": forecast_traffic_baseline([12, 14, 17, 18, 20, 23, 24, 27], horizon=6),
            "message": "Heuristic demonstration; no LSTM is trained."}

@router.get("/anomaly")
async def ml_anomaly() -> dict[str, object]:
    return {"status": "baseline", "methods": ["IsolationForestLite", "pure-Python TinyAutoencoder"],
            "message": "Scores are demonstration heuristics, not calibrated probabilities."}

@router.post("/anomaly/score")
async def ml_anomaly_score(request: Request) -> dict[str, object]:
    payload = await request.json()
    if isinstance(payload, list):
        sample = payload
    elif isinstance(payload, dict):
        sample = payload.get("sample")
    else:
        sample = None
    if not isinstance(sample, list) or len(sample) != len(FEATURES):
        raise HTTPException(status_code=422, detail="sample must be an array with six sensor values.")
    try:
        values = [float(value) for value in sample]
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail="sample values must be numeric.") from None
    if any(not (value == value and abs(value) < 1e12) for value in values):
        raise HTTPException(status_code=422, detail="sample values must be finite.")
    _, forest, autoencoder = _fitted_baselines()
    return {"status": "baseline", "method": "IsolationForestLite and pure-Python TinyAutoencoder",
            "isolation_score": forest.anomaly_score(values),
            "reconstruction_error": autoencoder.reconstruction_error(values),
            "features": list(FEATURES),
            "message": "Heuristic demonstration scores; not a trained neural detector or calibrated probability."}
