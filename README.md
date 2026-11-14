# SmartCity Sentinel

Privacy-first smart-city monitoring **simulation**. The default demo is offline, uses generated data, writes only local CSV/JSON/JSONL files, and needs only Python's standard library. Optional integrations are disabled unless explicitly installed and configured. This is a prototype, not an operational surveillance or emergency-response product.

## Quick start

```powershell
python main.py --demo
python -m unittest discover -s tests -v
python main.py --serve-api
```

The demo never opens a camera, sends network requests, or stores video. It generates sample data under `data/` and applies the seven-day retention helper only to `data/retained/`.

## Analytics methods

Traffic forecasting uses a small recent-trend heuristic (`forecast_traffic_baseline`), not an LSTM. Anomaly examples use `IsolationForestLite` and a pure-Python `TinyAutoencoder`; these are compact demonstrations, and their scores are not calibrated probabilities or production models. The repository does not train neural networks or claim trained model artifacts.

The demo also includes crowd density and congestion risk, environmental thresholds, Dijkstra route planning, privacy helpers, fairness summaries, a tabular Q-learning toy signal controller, local FastAPI/WebSocket service, static website, and optional Streamlit dashboard.

## Local API and website

Install the packages in `requirements.txt`, then start the loopback-only API and website:

```powershell
pip install -r requirements.txt
python main.py --serve-api
```

Open `http://127.0.0.1:8000/site/`. The site has four main pages:

- **Home** (`/site/`): a generated-data overview and the path an alert takes through the service.
- **Dashboard** (`/site/dashboard.html`): in-memory alerts, generated sensor metrics, route, crowd estimate, and audit examples.
- **Lab** (`/site/lab.html`): guided experiments that call the `/tools/` API on generated or user-adjusted values.
- **Limits** (`/site/limits.html`): implementation facts, boundaries, and evidence needed before making stronger claims.

The optional analytics page is at `/site/ml.html`. API documentation is available at `http://127.0.0.1:8000/docs`. The API creates its demo state in a temporary directory; `python main.py --demo` remains the explicit command that writes demo files under `data/`.

## Optional video adapter

Install `ultralytics` and OpenCV separately, then provide an existing local model artifact to `LocalYoloTracker(model_path=...)`. The adapter does not download weights. Only use authorized footage; the repository intentionally includes no face recognition or raw-video retention pipeline. Offline EasyOCR initialization requires its weights to already exist locally.

## Security and dependencies

The `role_allows` helper is an example permission check and is not connected to API routes. The API has no authentication; keep it bound to `127.0.0.1:8000` and do not expose this prototype publicly. The offline demo uses only Python's standard library (3.10+). Optional API, dashboard, testing, and local video packages are listed in `requirements.txt`. PyTorch is not a dependency.
