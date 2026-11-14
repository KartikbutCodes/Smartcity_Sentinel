"""FastAPI endpoints backed by in-memory event state and an asyncio queue."""

from __future__ import annotations

import asyncio
import csv
import json
import random
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from smartcity_sentinel.modules.operations import DEMO_CITY_GRAPH


async def _load_demo_state(
    data_directory: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, Any]]:
    from main import run_demo
    from smartcity_sentinel.modules.privacy.controls import minimize_event

    demo_values = await run_demo(data_directory)

    with (data_directory / "demo_events.json").open(encoding="utf-8") as file:
        raw_events = json.load(file)
    if not isinstance(raw_events, list) or not all(isinstance(event, dict) for event in raw_events):
        raise RuntimeError("Demo event data must be a list of JSON objects.")
    events = [minimize_event(event) for event in raw_events]

    sensor_readings: list[dict[str, Any]] = []
    with (data_directory / "sensor_readings.csv").open(newline="", encoding="utf-8") as file:
        for row in csv.DictReader(file):
            reading: dict[str, Any] = {"timestamp": row["timestamp"]}
            for key, value in row.items():
                if key != "timestamp" and value is not None:
                    reading[key] = float(value)
            sensor_readings.append(reading)
    demo_values["sensor_readings"] = sensor_readings

    route_result = demo_values.get("response_route")
    if not isinstance(route_result, tuple) or len(route_result) != 2:
        raise RuntimeError("Demo route data has an unexpected shape.")
    route_path, route_distance = route_result
    route = {"path": route_path, "distance": route_distance}
    audit_path = data_directory / "audit.jsonl"
    if audit_path.exists():
        demo_values["audit_chain"] = [
            json.loads(line)
            for line in audit_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
    return events, demo_values, route


def create_app() -> Any:
    """Create the API app, importing optional web dependencies on demand."""
    try:
        from fastapi import FastAPI, WebSocket, WebSocketDisconnect
        from fastapi.responses import RedirectResponse
        from fastapi.staticfiles import StaticFiles
    except ImportError as error:
        raise RuntimeError("Install FastAPI and uvicorn to run the REST/WebSocket API.") from error

    async def publish_alert(event: dict[str, Any]) -> None:
        app.state.events.append(event)
        for subscriber in tuple(app.state.subscribers):
            await subscriber.put(event)

    @asynccontextmanager
    async def lifespan(app: Any):
        from smartcity_sentinel.api.tools import build_anomaly_models

        with tempfile.TemporaryDirectory(prefix="smartcity-sentinel-api-") as temp_dir:
            data_directory = Path(temp_dir)
            app.state.events, app.state.metrics, app.state.route = await _load_demo_state(data_directory)
            app.state.anomaly_models = build_anomaly_models()
            templates = tuple(dict(event) for event in app.state.events)
            if not templates:
                raise RuntimeError("Generated alert dataset is empty.")

            async def emit_live_alerts() -> None:
                sequence = 1
                while True:
                    await asyncio.sleep(5)
                    template = random.choice(templates)
                    event = dict(template)
                    event["id"] = f"live-{sequence:04d}"
                    event["timestamp"] = datetime.now(timezone.utc).isoformat()
                    kind = str(event.get("kind", "event") or "event")
                    event["kind"] = kind
                    severity = float(event.get("severity", 0.0) or 0.0)
                    event["severity"] = min(1.0, max(0.0, severity + random.uniform(-0.08, 0.08)))
                    event["description"] = f"Live simulated {kind.replace('_', ' ')} signal"
                    event["metadata"] = dict(template.get("metadata", {}))
                    await publish_alert(event)
                    sequence += 1

            producer = asyncio.create_task(emit_live_alerts())
            try:
                yield
            finally:
                producer.cancel()
                try:
                    await producer
                except asyncio.CancelledError:
                    pass

    app = FastAPI(title="SmartCity Sentinel", lifespan=lifespan)
    app.state.events = []
    app.state.subscribers = set()
    from smartcity_sentinel.api.ml import router as ml_router
    from smartcity_sentinel.api.tools import router as tools_router
    app.include_router(tools_router)
    app.include_router(ml_router)

    @app.get("/", include_in_schema=False)
    async def home():
        return RedirectResponse("/site/", status_code=307)

    @app.get("/health")
    async def health() -> dict[str, str]:
        """Return basic service state."""
        return {"status": "ok", "mode": "local"}

    @app.get("/alerts")
    async def alerts() -> list[dict[str, Any]]:
        """List in-memory alerts."""
        return list(app.state.events)

    @app.get("/metrics")
    async def metrics() -> dict[str, Any]:
        """Return the generated local metrics."""
        return {**app.state.metrics, "alert_count": len(app.state.events)}

    @app.get("/route")
    async def route() -> dict[str, Any]:
        """Return the generated response route."""
        return app.state.route

    @app.get("/city")
    async def city() -> dict[str, dict[str, float]]:
        """Return the read-only route graph used by the city map."""
        return DEMO_CITY_GRAPH

    @app.post("/alerts")
    async def ingest_alert(event: dict[str, Any]) -> dict[str, str]:
        """Accept metadata-only events; raw image payloads are not accepted."""
        def reject_raw_media(value: Any, path: str = "event") -> None:
            if isinstance(value, dict):
                for key, child in value.items():
                    normalized = str(key).casefold()
                    if "image" in normalized or "frame" in normalized or "video" in normalized:
                        from fastapi import HTTPException
                        raise HTTPException(status_code=400, detail=f"Raw media field {path}.{key} is not accepted.")
                    reject_raw_media(child, f"{path}.{key}")
            elif isinstance(value, list):
                for index, child in enumerate(value):
                    reject_raw_media(child, f"{path}[{index}]")

        reject_raw_media(event)
        if not event.get("id"):
            event["id"] = f"ingested-{uuid4().hex}"
        if not event.get("timestamp"):
            event["timestamp"] = datetime.now(timezone.utc).isoformat()
        if not event.get("kind"):
            event["kind"] = "unspecified"
        if not event.get("severity"):
            event["severity"] = 0.0
        if not event.get("description"):
            event["description"] = "Ingested metadata alert"
        await publish_alert(event)
        return {"status": "queued"}

    async def alert_stream(websocket: WebSocket) -> None:
        """Stream alerts to connected dashboard clients."""
        await websocket.accept()
        subscriber: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        app.state.subscribers.add(subscriber)
        try:
            while True:
                await websocket.send_json(await subscriber.get())
        except WebSocketDisconnect:
            pass
        finally:
            app.state.subscribers.discard(subscriber)

    # FastAPI needs the concrete class because this module postpones annotations.
    alert_stream.__annotations__["websocket"] = WebSocket
    app.add_api_websocket_route("/ws/alerts", alert_stream)

    web_directory = Path(__file__).resolve().parents[1] / "web"
    app.mount("/site", StaticFiles(directory=web_directory, html=True), name="site")

    return app
