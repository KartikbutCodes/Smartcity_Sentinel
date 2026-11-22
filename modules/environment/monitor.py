"""Offline environmental forecasting and threshold alerts."""

from __future__ import annotations

from collections.abc import Sequence


def forecast_arima_baseline(values: Sequence[float], horizon: int = 1) -> list[float]:
    """Forecast by extrapolating a damped first-difference trend."""
    if not values or horizon < 1:
        raise ValueError("Values and a positive horizon are required.")
    trend = values[-1] - values[-2] if len(values) > 1 else 0.0
    forecast = []
    current = values[-1]
    for _ in range(horizon):
        current += trend * 0.5
        forecast.append(current)
        trend *= 0.5
    return forecast


def threshold_alerts(reading: dict[str, float]) -> list[dict[str, str | float]]:
    """Emit AQI and flood warnings when the configured demo limits are crossed."""
    alerts = []
    limits = {"aqi": 150.0, "flood_level_m": 0.6, "noise_db": 85.0}
    for field, threshold in limits.items():
        value = reading.get(field)
        if value is not None and value >= threshold:
            alerts.append({"kind": field, "value": value, "threshold": threshold})
    return alerts
