"""API and local tool endpoint tests; skipped when TestClient requirements are absent."""

from __future__ import annotations

import importlib.util
import unittest

HAS_TEST_CLIENT = importlib.util.find_spec("fastapi") is not None and importlib.util.find_spec("httpx") is not None

if HAS_TEST_CLIENT:
    from fastapi.testclient import TestClient
    from smartcity_sentinel.api.app import create_app


@unittest.skipUnless(HAS_TEST_CLIENT, "FastAPI TestClient requires optional fastapi and httpx packages.")
class ApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.client_context = TestClient(create_app())
        cls.client = cls.client_context.__enter__()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.client_context.__exit__(None, None, None)

    def test_core_read_endpoints(self) -> None:
        self.assertEqual(self.client.get("/health").json()["status"], "ok")
        alerts = self.client.get("/alerts")
        self.assertEqual(alerts.status_code, 200)
        self.assertTrue(alerts.json())
        metrics = self.client.get("/metrics").json()
        self.assertIn("crowd_risk", metrics)
        self.assertEqual(len(metrics["sensor_readings"]), 48)
        self.assertEqual(self.client.get("/route").json()["path"], ["Central", "North", "Market"])
        self.assertIn("Central", self.client.get("/city").json())

    def test_post_alert_defaults_and_rejects_raw_media(self) -> None:
        self.assertEqual(self.client.post("/alerts", json={"metadata": {"image_data": "x"}}).status_code, 400)
        response = self.client.post("/alerts", json={"kind": "test"})
        self.assertEqual(response.status_code, 200)
        event = self.client.get("/alerts").json()[-1]
        self.assertTrue(event["id"])
        self.assertTrue(event["timestamp"])
        self.assertEqual(event["kind"], "test")

        response = self.client.post("/alerts", json={})
        self.assertEqual(response.status_code, 200)
        event = self.client.get("/alerts").json()[-1]
        self.assertTrue(event["id"])
        self.assertTrue(event["timestamp"])
        self.assertEqual(event["kind"], "unspecified")
        self.assertEqual(event["severity"], 0.0)
        self.assertEqual(event["description"], "Ingested metadata alert")

    def test_route_priority_and_plate_tools(self) -> None:
        self.assertEqual(self.client.post("/tools/route", json={"start": "Central", "destination": "Market"}).json()["distance"], 4.0)
        self.assertEqual(self.client.post("/tools/route", json={"start": "Unknown", "destination": "Market"}).status_code, 422)
        self.assertEqual(self.client.post("/tools/priority", json={"severity": 0.8}).status_code, 200)
        self.assertEqual(self.client.post("/tools/priority", json={"severity": 1.1}).status_code, 422)
        self.assertTrue(self.client.post("/tools/plate", json={"text": "KA 03 MN 1234"}).json()["valid"])
        self.assertEqual(self.client.post("/tools/plate", json={}).status_code, 422)
        self.assertIn("graph", self.client.get("/tools/nodes").json())

    def test_speed_and_virtual_line_tools(self) -> None:
        speed = self.client.post("/tools/speed", json={
            "first_point": [0, 0], "second_point": [6, 8], "elapsed_seconds": 2,
            "homography": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        })
        self.assertEqual(speed.status_code, 200)
        self.assertEqual(speed.json()["speed_mps"], 5.0)
        self.assertEqual(self.client.post("/tools/speed", json={
            "first_point": [0, 0], "second_point": [1, 1], "elapsed_seconds": 0,
            "homography": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        }).status_code, 422)
        crossed = self.client.post("/tools/line-counter", json={
            "line_y": 10, "positions": [{"track_id": 1, "center_y": 5}, {"track_id": 1, "center_y": 12}],
        })
        self.assertEqual(crossed.json()["count"], 1)
        self.assertEqual(self.client.post("/tools/line-counter", json={
            "line_y": 10, "positions": [{"track_id": 1, "center_y": 5}] * 101,
        }).status_code, 422)

    def test_crowd_forecast_rul_and_anomaly_tools(self) -> None:
        self.assertEqual(len(self.client.get("/tools/crowd").json()["grid"]), 8)
        custom_crowd = self.client.post("/tools/crowd", json={"points": [[0.5, 0.5], [0.51, 0.51]]})
        self.assertEqual(custom_crowd.status_code, 200)
        self.assertEqual(custom_crowd.json()["grid"][4][4], 2)
        self.assertEqual(self.client.post("/tools/crowd", json={"points": [[1.1, 0.5]]}).status_code, 422)
        forecast = self.client.post("/tools/forecast", json={"series": [1, 2, 3], "horizon": 2})
        self.assertEqual(forecast.status_code, 200)
        self.assertEqual(forecast.json()["traffic"]["label"], "BASELINE")
        self.assertEqual(self.client.post("/tools/forecast", json={"series": [1] * 501}).status_code, 422)
        self.assertIsNone(self.client.post("/tools/rul", json={
            "degradation": [4, 3, 2], "failure_threshold": 8,
        }).json()["remaining_useful_life"])
        self.assertEqual(self.client.post("/tools/rul", json={"degradation": [], "failure_threshold": 8}).status_code, 422)
        self.assertEqual(self.client.post("/tools/anomaly", json={"sample": [80, 310, 0.3]}).status_code, 200)
        self.assertEqual(self.client.post("/tools/anomaly", json={"sample": [80, 310]}).status_code, 422)

    def test_spot_anomaly_round(self) -> None:
        round_data = self.client.get("/tools/spot-anomaly").json()
        self.assertEqual(len(round_data["series"]), 6)
        score = self.client.post("/tools/spot-anomaly/score", json={"guess_index": 0, "seed": round_data["seed"]})
        self.assertEqual(score.status_code, 200)
        self.assertEqual(len(score.json()["scores"]), 6)
        self.assertIn("correct", score.json())
        self.assertEqual(self.client.post("/tools/spot-anomaly/score", json={"guess_index": 6}).status_code, 422)

    def test_privacy_and_audit_tools(self) -> None:
        noisy = self.client.post("/tools/noisy-count", json={"count": 14, "epsilons": [0.5, 1]})
        self.assertEqual(len(noisy.json()["runs"][0]["samples"]), 50)
        self.assertEqual(self.client.post("/tools/noisy-count", json={"count": 14, "epsilons": [0]}).status_code, 422)
        minimized = self.client.post("/tools/minimize", json={
            "kind": "crowd_density", "metadata": {"source": "edge-1", "name": "removed"},
        })
        self.assertNotIn("name", minimized.json()["after"]["metadata"])
        self.assertEqual(self.client.post("/tools/minimize", json={
            "metadata": {"nested": {"raw_frame": "x"}},
        }).status_code, 422)
        audit = self.client.get("/tools/audit-chain").json()
        self.assertTrue(audit["valid_before_tamper"])
        self.assertFalse(audit["valid_after_tamper"])
        self.assertEqual(audit["tampered_block"], 3)
        clean_chain = self.client.get("/tools/audit-chain/sample").json()
        self.assertTrue(clean_chain["valid"])
        self.assertEqual(len(clean_chain["blocks"]), 5)
        changed_chain = self.client.post("/tools/audit-chain/tamper", json={"block_number": 2})
        self.assertEqual(changed_chain.status_code, 200)
        self.assertEqual([block["valid"] for block in changed_chain.json()["blocks"]], [True, False, False, False, False])
        self.assertEqual(self.client.post("/tools/audit-chain/tamper", json={"block_number": 6}).status_code, 422)

    def test_roles_and_bias_tools(self) -> None:
        self.assertIn("admin", self.client.get("/tools/roles").json())
        self.assertTrue(self.client.get("/tools/role-check", params={"role": "officer", "permission": "read_alerts"}).json()["allowed"])
        self.assertEqual(self.client.get("/tools/role-check").status_code, 422)
        bias = self.client.get("/tools/bias").json()
        self.assertTrue(bias["warnings"])
        self.assertEqual(self.client.get("/tools/bias").status_code, 200)

    def test_fedavg_edge_and_edge_cloud_tools(self) -> None:
        self.assertEqual(self.client.post("/tools/fedavg", json={
            "node_weights": [[0, 2], [2, 4]], "sample_counts": [1, 3],
        }).json()["weights"], [1.5, 3.5])
        self.assertEqual(self.client.post("/tools/fedavg", json={
            "node_weights": [[1], [1]], "sample_counts": [1, 0],
        }).status_code, 422)
        self.assertFalse(self.client.post("/tools/edge", json={
            "detections": [{"label": "person", "confidence": 0.9}],
        }).json()["raw_frame_included"])
        self.assertEqual(self.client.post("/tools/edge", json={
            "detections": [{"label": "person", "confidence": 1.2}],
        }).status_code, 422)
        self.assertIn("bandwidth_reduction_ratio", self.client.get("/tools/edge-cloud").json())
        comparison = self.client.post("/tools/edge-cloud", json={
            "source_bytes": 1000, "metadata_bytes": 100, "item_count": 5,
            "edge_latency_ms": 10, "cloud_latency_ms": 50,
        })
        self.assertEqual(comparison.status_code, 200)
        self.assertEqual(comparison.json()["edge_uplink_bytes"], 500)
        self.assertEqual(self.client.post("/tools/edge-cloud", json={"source_bytes": 0}).status_code, 422)

    def test_q_learning_and_video_event_tools(self) -> None:
        q_result = self.client.post("/tools/q-learning", json={"episodes": 2})
        self.assertEqual(q_result.status_code, 200)
        self.assertEqual(len(q_result.json()["reward_curve"]), 2)
        self.assertEqual(len(q_result.json()["random_baseline"]), 2)
        self.assertEqual(self.client.post("/tools/q-learning", json={"episodes": 301}).status_code, 422)
        self.assertTrue(self.client.post("/tools/video-events", json={"scenario": "loitering"}).json()["events"])
        self.assertEqual(self.client.post("/tools/video-events", json={"scenario": "unknown"}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
