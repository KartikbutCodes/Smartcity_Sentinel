"""Command-line entry point for the synthetic SmartCity Sentinel demo."""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from smartcity_sentinel.data.generate import generate_demo_events, generate_sensor_rows, write_demo_data
from smartcity_sentinel.modules.anomaly.detectors import IsolationForestLite, TinyAutoencoder
from smartcity_sentinel.modules.crowd.density import density_grid, stampede_risk
from smartcity_sentinel.modules.edge_sim.simulation import EdgeNode, compare_edge_cloud, fedavg
from smartcity_sentinel.modules.environment.monitor import threshold_alerts
from smartcity_sentinel.modules.fairness.audit import bias_audit
from smartcity_sentinel.modules.privacy.controls import (
    HashChainAuditLog,
    laplace_noisy_count,
    minimize_event,
    purge_expired_files,
)
from smartcity_sentinel.modules.traffic.analytics import SignalQLearner, forecast_traffic_baseline
from smartcity_sentinel.modules.operations import DEMO_CITY_GRAPH, prioritize_alert, shortest_route


async def run_demo(data_dir: Path) -> dict[str, object]:
    """Exercise all core subsystems using generated data, without network access."""
    csv_path, json_path = write_demo_data(data_dir, seed=17)
    expired_files = purge_expired_files(data_dir / "retained", retention_days=7)
    rows = generate_sensor_rows(seed=17)
    features = [[row["power_kw"], row["water_pressure_kpa"], row["bridge_vibration"]] for row in rows[:30]]
    forest = IsolationForestLite().fit(features)
    autoencoder = TinyAutoencoder().fit(features)
    latest = [rows[44]["power_kw"], rows[44]["water_pressure_kpa"], rows[44]["bridge_vibration"]]

    event_list = [minimize_event(event) for event in generate_demo_events()]
    audit = HashChainAuditLog(data_dir / "audit.jsonl")
    audit.append("demo", "generated_synthetic_alerts", {"count": len(event_list)})
    edge_output = EdgeNode("edge-01").infer_metadata(
        [{"label": "vehicle", "confidence": 0.93}, {"label": "person", "confidence": 0.64}]
    )
    learner = SignalQLearner()
    learner.train(episodes=50)
    points = [(index / 20, (index % 10) / 10) for index in range(14)]
    density = density_grid(points)

    # Event queue is process-local; this verifies async event delivery in demo mode.
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue()
    for event in event_list:
        await queue.put(event)
    queued = queue.qsize()
    forecast = forecast_traffic_baseline([12, 14, 17, 18, 20, 23, 24, 27], horizon=3)
    result: dict[str, object] = {
        "mode": "offline-synthetic",
        "generated_files": [str(csv_path), str(json_path)],
        "expired_retained_files_deleted": len(expired_files),
        "sensor_rows": len(rows),
        "anomaly_scores": {
            "isolation_forest": round(forest.anomaly_score(latest), 4),
            "autoencoder_reconstruction_error": round(autoencoder.reconstruction_error(latest), 4),
        },
        "environment_alerts": threshold_alerts(rows[-2]),
        "crowd_risk": round(stampede_risk(density), 3),
        "traffic_forecast_baseline": [round(value, 2) for value in forecast],
        "q_learning_states": len(learner.q_values),
        "fedavg_example": fedavg([[0.2, 0.4], [0.4, 0.6], [0.3, 0.5]], [10, 20, 10]),
        "edge_metadata_example": edge_output,
        "edge_cloud": compare_edge_cloud(),
        "privacy_noisy_count": round(laplace_noisy_count(14, epsilon=1, seed=17), 2),
        "audit_chain_valid": audit.verify(),
        "queued_demo_alerts": queued,
        "first_alert_priority": prioritize_alert(float(event_list[0]["severity"])),
        "response_route": shortest_route(DEMO_CITY_GRAPH, "Central", "Market"),
        "fairness_example": bias_audit(
            [{"group": "A", "actual": 1, "predicted": 0}, {"group": "B", "actual": 0, "predicted": 1}]
        ),
    }
    return result


def main() -> None:
    """Parse command-line options and run the offline demonstration."""
    parser = argparse.ArgumentParser(description="Offline SmartCity Sentinel demo")
    parser.add_argument("--demo", action="store_true", help="run generated-data demonstration")
    parser.add_argument("--data-dir", type=Path, default=Path(__file__).parent / "data")
    parser.add_argument("--serve-api", action="store_true", help="start optional local FastAPI service")
    args = parser.parse_args()
    if args.serve_api:
        try:
            import uvicorn
        except ImportError as error:
            raise SystemExit("Install uvicorn and fastapi first: pip install -r requirements.txt") from error
        from smartcity_sentinel.api.app import create_app
        uvicorn.run(create_app(), host="127.0.0.1", port=8000)
        return
    if not args.demo:
        parser.error("Choose --demo or --serve-api.")
    print(json.dumps(asyncio.run(run_demo(args.data_dir)), indent=2))


if __name__ == "__main__":
    main()
