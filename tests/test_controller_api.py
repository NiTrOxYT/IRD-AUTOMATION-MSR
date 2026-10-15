import unittest
from app.main import app
from app.controller_automation.router import (
    get_controller_status,
    get_controller_settings,
    update_controller_settings,
    list_controller_history,
    list_controller_sites,
    stop_controller_run,
    get_controller_metrics
)
from app.controller_automation.models import ControllerSettingsUpdate


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


class TestControllerApi(unittest.IsolatedAsyncioTestCase):
    def test_routes_registered_in_fastapi(self):
        registered_paths = _get_all_app_paths()
        expected_routes = [
            "/api/controller/status",
            "/api/controller/run",
            "/api/controller/test-connection",
            "/api/controller/stop",
            "/api/controller/history",
            "/api/controller/history/{run_uuid}",
            "/api/controller/settings",
            "/api/controller/metrics",
            "/api/controller/sites"
        ]
        for path in expected_routes:
            self.assertIn(path, registered_paths, f"Route '{path}' missing from FastAPI router!")

    async def test_get_controller_status(self):
        status = await get_controller_status()
        self.assertIsNotNone(status)
        self.assertIn(status.status, ["IDLE", "RUNNING", "SUCCESS", "FAILED", "STOPPED"])
        self.assertIsInstance(status.steps, list)

    async def test_get_and_update_settings(self):
        settings = await get_controller_settings()
        self.assertIn("jump_host", settings)
        self.assertEqual(settings["jump_host"], "111.93.205.187")

        # Update a setting
        update_res = await update_controller_settings(ControllerSettingsUpdate(site_default_port=22))
        self.assertEqual(update_res["status"], "UPDATED")

    async def test_list_controller_history(self):
        history = await list_controller_history(limit=10)
        self.assertIsInstance(history, list)

    async def test_list_controller_sites(self):
        sites = await list_controller_sites()
        self.assertIsInstance(sites, list)
        if len(sites) > 0:
            self.assertIn("site_ip", sites[0])
            self.assertIn("name", sites[0])

    async def test_stop_controller_run_idle(self):
        res = await stop_controller_run()
        self.assertEqual(res["status"], "NOT_RUNNING")

    async def test_get_controller_metrics(self):
        metrics = await get_controller_metrics()
        self.assertIn("total_runs", metrics)
        self.assertIn("successful_runs", metrics)
        self.assertIn("failed_runs", metrics)

    async def test_start_controller_run_handler(self):
        from unittest.mock import patch
        from app.controller_automation.models import ControllerCloneRequest
        from app.controller_automation.router import start_controller_run

        req = ControllerCloneRequest(
            site_id=22,
            site_name="ITC Grand Chola",
            site_ip="14.142.185.130",
            site_port=22,
            current_room_no="2810",
            current_room_ip="10.172.28.110",
            similar_room_no="2108",
            similar_room_ip="10.172.21.108",
            is_new_controller=False
        )

        with patch("app.controller_automation.workflow_runner.ControllerWorkflowRunner.start_run", return_value="run_test_abc"):
            res = await start_controller_run(req)
            self.assertEqual(res["status"], "STARTED")
            self.assertEqual(res["run_uuid"], "run_test_abc")
            self.assertEqual(res["target_ip"], "10.172.28.110")


if __name__ == "__main__":
    unittest.main()
