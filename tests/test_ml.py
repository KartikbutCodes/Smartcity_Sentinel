from __future__ import annotations

import asyncio
import builtins
import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

HAS_FASTAPI_CLIENT = importlib.util.find_spec("fastapi") is not None and importlib.util.find_spec("httpx") is not None
if HAS_FASTAPI_CLIENT:
    from fastapi.testclient import TestClient
    from smartcity_sentinel.api.app import create_app

class TorchFreeTests(unittest.TestCase):
    def test_default_demo_and_active_imports_do_not_require_torch(self) -> None:
        original_import = builtins.__import__
        def no_torch(name, *args, **kwargs):
            if name == "torch" or name.startswith("torch."):
                raise AssertionError("active code attempted to import torch")
            return original_import(name, *args, **kwargs)
        with tempfile.TemporaryDirectory() as directory, patch("builtins.__import__", side_effect=no_torch):
            import main
            result = asyncio.run(main.run_demo(Path(directory)))
            from smartcity_sentinel.modules.traffic.analytics import forecast_traffic_baseline
            self.assertEqual(len(forecast_traffic_baseline([1, 2, 3], horizon=2)), 2)
            self.assertEqual(result["mode"], "offline-synthetic")

@unittest.skipUnless(HAS_FASTAPI_CLIENT, "FastAPI TestClient requires optional fastapi and httpx packages.")
class BaselineApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.context = TestClient(create_app())
        cls.client = cls.context.__enter__()
    @classmethod
    def tearDownClass(cls):
        cls.context.__exit__(None, None, None)
    def test_analytics_page_is_served_and_names_baselines(self):
        response = self.client.get("/site/ml.html")
        self.assertEqual(response.status_code, 200)
        self.assertIn("dependency-free heuristic examples", response.text)
        script = self.client.get("/site/js/ml-page.js")
        self.assertEqual(script.status_code, 200)
        self.assertIn("/ml/traffic", script.text)

    def test_analytics_page_is_reachable_from_site_navigation(self):
        for page in ("/site/", "/site/dashboard.html", "/site/lab.html", "/site/limits.html", "/site/ml.html"):
            response = self.client.get(page)
            self.assertEqual(response.status_code, 200, page)
            self.assertIn('href="/site/ml.html"', response.text, page)

    def test_status_and_traffic_are_baselines(self):
        status = self.client.get("/ml/status").json()
        self.assertEqual(status["status"], "baseline")
        self.assertFalse(status["models_trained"])
        self.assertEqual(self.client.get("/ml/traffic").json()["status"], "baseline")
    def test_anomaly_baseline_scoring(self):
        response = self.client.post("/ml/anomaly/score", json={"sample": [82.5, 328.0, .23, 58.0, 47.0, .12]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "baseline")
        self.assertIn("reconstruction_error", response.json())
        self.assertEqual(self.client.post("/ml/anomaly/score", json={"sample": [1]}).status_code, 422)

if __name__ == "__main__":
    unittest.main()
