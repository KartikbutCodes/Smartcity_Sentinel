# SmartCity Sentinel Project Report

## Scope and execution

SmartCity Sentinel is an offline, privacy-first smart-city monitoring simulation. Its default command, `python main.py --demo`, generates synthetic data and exercises traffic, anomaly, crowd, environment, privacy, fairness, routing, edge-simulation, and alert examples. It does not connect to actual city sensors and does not train a neural network.

## Analytics

- Traffic forecast: `forecast_traffic_baseline` extrapolates a small portion of the recent trend. It is a heuristic, not an LSTM or a trained forecasting model.
- Anomaly examples: `IsolationForestLite` and `TinyAutoencoder` are dependency-free demonstrations fit to generated rows. Their outputs are illustrative scores, not calibrated probabilities.
- Other calculations include crowd occupancy risk, environmental thresholds, a tabular Q-learning signal-control simulation, fairness error summaries, and Dijkstra route planning.

No PyTorch training code, model-loading path, or Grad-CAM function is part of the project. The CLI offers `--demo` and `--serve-api`; it does not offer a neural training command. The `/ml/` API endpoints and analytics page report heuristic baselines and clearly state that no neural network is trained.

## Interfaces and optional dependencies

The optional FastAPI service serves HTTP routes, WebSocket alerts, and static assets under `/site`. A separate optional Streamlit dashboard reads local generated data. The optional local video adapter accepts an existing local YOLO model artifact and does not download weights. API authentication is not included; keep the service bound to loopback.

The offline demonstration and core algorithms use the Python standard library. FastAPI, Uvicorn, WebSockets, Streamlit, test support, and optional video libraries are listed or described in `requirements.txt`. PyTorch is not required.

## Verification commands

```powershell
python -m unittest discover -s tests -v
python main.py --demo
```
