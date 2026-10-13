import os
import unittest
import asyncio
from pathlib import Path

from app.main import app
from app.dth_automation.router import (
    download_template,
    validate_file,
    get_execution_status,
    get_history,
    get_categories,
    get_selectors,
    update_selector
)
from app.dth_automation.models import DthExecutionMode, StartDthRunRequest


def _get_all_app_paths():
    paths = []
    for r in app.routes:
        if hasattr(r, "original_router") and hasattr(r, "include_context"):
            prefix = getattr(r.include_context, "prefix", "")
            for sub in r.original_router.routes:
                if hasattr(sub, "path"):
                    paths.append(f"{prefix}{sub.path}")
        elif hasattr(r, "path"):
            paths.append(r.path)
    return paths


class TestDthApi(unittest.IsolatedAsyncioTestCase):
    def test_routes_registered_in_fastapi(self):
        registered_paths = _get_all_app_paths()
        expected_dth_routes = [
            "/api/dth/template",
            "/api/dth/upload",
            "/api/dth/validate",
            "/api/dth/execute",
            "/api/dth/status",
            "/api/dth/stop",
            "/api/dth/history",
            "/api/dth/runs/{run_id}",
            "/api/dth/reports/{run_id}/csv",
            "/api/dth/reports/{run_id}/json",
            "/api/dth/categories",
            "/api/dth/selectors"
        ]
        for path in expected_dth_routes:
            self.assertIn(path, registered_paths, f"Route '{path}' missing from FastAPI router!")

    def test_existing_ird_routes_preserved(self):
        registered_paths = _get_all_app_paths()
        expected_ird_routes = [
            "/api/health",
            "/api/sites",
            "/api/settings",
            "/api/automation/start-sync",
            "/api/automation/stop",
            "/api/runs",
            "/api/integration-test/run"
        ]
        for path in expected_ird_routes:
            self.assertIn(path, registered_paths, f"Existing IRD route '{path}' was removed or broken!")

    async def test_template_download_csv(self):
        res = await download_template(format="csv")
        self.assertIsNotNone(res)
        self.assertEqual(res.media_type, "text/csv")
        self.assertTrue(os.path.exists(res.path))

    async def test_template_download_xlsx(self):
        res = await download_template(format="xlsx")
        self.assertIsNotNone(res)
        self.assertIn("spreadsheetml", res.media_type)
        self.assertTrue(os.path.exists(res.path))

    async def test_categories_endpoint(self):
        res = await get_categories()
        self.assertTrue(res["success"])
        self.assertIn("all", res["categories"])
        self.assertIn("News", res["categories"])

    async def test_selectors_endpoint(self):
        res = await get_selectors()
        self.assertTrue(res["success"])
        self.assertIn("input_channel_number", res["selectors"])
        self.assertIn("btn_save_channel", res["selectors"])

    async def test_update_selector_override(self):
        update_res = await update_selector("custom_test_btn", "#customBtn, .btn-custom")
        self.assertTrue(update_res["success"])
        self.assertEqual(update_res["selectors"], ["#customBtn", ".btn-custom"])

    async def test_execution_status_endpoint(self):
        status = await get_execution_status()
        self.assertIn("is_running", status)
        self.assertIn("status", status)
        self.assertIn("mode", status)

    async def test_history_endpoint(self):
        hist = await get_history(limit=10)
        self.assertTrue(hist["success"])
        self.assertIsInstance(hist["runs"], list)


if __name__ == "__main__":
    unittest.main()
