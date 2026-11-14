"""Simple Streamlit dashboard for synthetic incident and sensor data."""

from __future__ import annotations

import json
import csv
from pathlib import Path


def main() -> None:
    """Render the local operations dashboard."""
    try:
        import streamlit as st
    except ImportError as error:
        raise RuntimeError("Install streamlit to launch the dashboard.") from error
    data_dir = Path(__file__).resolve().parents[2] / "data"
    events_path = data_dir / "demo_events.json"
    events = json.loads(events_path.read_text(encoding="utf-8")) if events_path.exists() else []
    st.set_page_config(page_title="SmartCity Sentinel", layout="wide")
    st.title("SmartCity Sentinel")
    st.caption("Local operational view · no live cameras or personal identities")
    st.warning("Alerts require human verification; do not use for enforcement.")
    scene_path = data_dir / "sample_scene.svg"
    if scene_path.exists():
        st.subheader("Simulated scene")
        st.image(str(scene_path), caption="Synthetic illustration; this is not a live feed.")
    st.subheader("Incident feed")
    st.dataframe(events, use_container_width=True)
    st.subheader("Incident locations (synthetic)")
    coordinates = {
        "Central Junction": (12.9716, 77.5946),
        "River Ward": (12.9650, 77.6100),
        "North Bridge": (12.9900, 77.5900),
        "Market Square": (12.9760, 77.5800),
    }
    mapped = [
        {"lat": coordinates[event["location"]][0], "lon": coordinates[event["location"]][1]}
        for event in events if event.get("location") in coordinates
    ]
    if mapped:
        st.map(mapped)
    readings_path = data_dir / "sensor_readings.csv"
    if readings_path.exists():
        with readings_path.open(newline="", encoding="utf-8") as file:
            readings = list(csv.DictReader(file))
        st.subheader("Synthetic sensor trends")
        st.line_chart(
            [{"AQI": float(row["aqi"]), "Noise (dB)": float(row["noise_db"])} for row in readings]
        )
    st.subheader("Privacy and governance")
    st.write("Raw footage is not shown or persisted by this dashboard. Audit log is local-only.")


if __name__ == "__main__":
    main()
