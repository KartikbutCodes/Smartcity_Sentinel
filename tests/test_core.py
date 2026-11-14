"""Tests for core algorithms, privacy protections, and local persistence."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from smartcity_sentinel.modules.anomaly.detectors import IsolationForestLite, TinyAutoencoder
from smartcity_sentinel.modules.crowd.density import density_grid, stampede_risk
from smartcity_sentinel.modules.edge_sim.simulation import fedavg
from smartcity_sentinel.modules.fairness.audit import bias_audit
from smartcity_sentinel.modules.privacy.controls import (
    HashChainAuditLog,
    laplace_noisy_count,
    purge_expired_files,
    role_allows,
)
from smartcity_sentinel.modules.traffic.analytics import VirtualLineCounter, project_homography, valid_indian_plate
from smartcity_sentinel.modules.operations import DEMO_CITY_GRAPH, prioritize_alert, shortest_route
from smartcity_sentinel.modules.video_analytics.events import Detection, EventDetector
from smartcity_sentinel.modules.edge_sim.simulation import EdgeNode


class CoreTests(unittest.TestCase):
    """Verify key math and governance invariants."""

    def test_virtual_line_counts_each_crossing(self) -> None:
        counter = VirtualLineCounter(10)
        self.assertFalse(counter.update(5, 5))
        self.assertTrue(counter.update(5, 12))
        self.assertFalse(counter.update(5, 14))
        self.assertEqual(counter.count, 1)

    def test_indian_plate_validation(self) -> None:
        self.assertTrue(valid_indian_plate("KA 03 MN 1234"))
        self.assertTrue(valid_indian_plate("BH 12 AB 1234"))
        self.assertFalse(valid_indian_plate("NOT-A-PLATE"))

    def test_density_and_risk(self) -> None:
        grid = density_grid([(1.0, 1.0), (0.0, 0.0), (1.1, 0.4)])
        self.assertEqual(grid[0][0], 1)
        self.assertEqual(grid[-1][-1], 1)
        self.assertGreater(stampede_risk(grid), 0)

    def test_anomaly_models_score_outlier_higher(self) -> None:
        normal = [[float(i), float(i % 3)] for i in range(20)]
        model = IsolationForestLite(trees=60, sample_size=20).fit(normal)
        self.assertGreater(model.anomaly_score([100.0, 40.0]), model.anomaly_score([9.0, 0.0]))
        ae = TinyAutoencoder().fit(normal)
        self.assertGreater(ae.reconstruction_error([100, 40]), ae.reconstruction_error([9, 0]))

    def test_privacy_audit_chain_and_roles(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            log = HashChainAuditLog(Path(directory) / "audit.jsonl")
            log.append("admin", "viewed_aggregate", {"count": 4})
            self.assertTrue(log.verify())
            with (Path(directory) / "audit.jsonl").open("a", encoding="utf-8") as file:
                file.write("{}\n")
            self.assertFalse(log.verify())
        self.assertTrue(role_allows("officer", "read_alerts"))
        self.assertFalse(role_allows("public", "read_audit"))
        self.assertGreaterEqual(laplace_noisy_count(10, seed=3), 0)

    def test_homography_and_fedavg(self) -> None:
        identity = [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        self.assertEqual(project_homography((2, 3), identity), (2, 3))
        self.assertEqual(fedavg([[0, 2], [2, 4]], [1, 3]), [1.5, 3.5])
        with self.assertRaises(ValueError):
            fedavg([[1], [1]], [1, 0])

    def test_bias_rates(self) -> None:
        result = bias_audit([
            {"group": "A", "actual": 0, "predicted": 1},
            {"group": "A", "actual": 1, "predicted": 0},
        ])
        self.assertEqual(result["A"]["false_positive_rate"], 1.0)
        self.assertEqual(result["A"]["false_negative_rate"], 1.0)

    def test_alert_routing_and_prioritization(self) -> None:
        self.assertEqual(shortest_route(DEMO_CITY_GRAPH, "Central", "Market"), (["Central", "North", "Market"], 4.0))
        self.assertEqual(prioritize_alert(1.0, 1.0, 1.0)["priority"], "high")
        with self.assertRaises(ValueError):
            shortest_route({"A": {"B": -1}, "B": {}}, "A", "B")

    def test_video_events_normalize_pixel_coordinates(self) -> None:
        detector = EventDetector(restricted_zone=(0.7, 0.1, 0.98, 0.9))
        detection = Detection("person", 0.9, (720, 200, 820, 400), track_id=12)
        events = detector.update([detection], timestamp=1.0, frame_size=(1000, 1000))
        self.assertIn({"kind": "restricted_zone_intrusion", "track_id": 12}, events)

    def test_retention_and_edge_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "old.json"
            path.write_text("synthetic", encoding="utf-8")
            os.utime(path, (100, 100))
            deleted = purge_expired_files(Path(directory), retention_days=1, now=100_000)
            self.assertEqual(deleted, [path])
        metadata = EdgeNode("edge-test").infer_metadata(
            [{"label": "person", "confidence": 0.9}, {"label": "vehicle", "confidence": 0.1}]
        )
        self.assertEqual(metadata["counts"], {"person": 1})
        self.assertFalse(metadata["raw_frame_included"])


if __name__ == "__main__":
    unittest.main()
