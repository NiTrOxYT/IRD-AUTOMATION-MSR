import os
import unittest
import asyncio
from pathlib import Path

from app.main import app
from app.action_point_automation.router import (
    upload_and_validate_file,
    get_action_point_status,
    stop_action_point_run,
    list_action_point_runs,
    get_action_point_run
)
from app.database.db import (
    init_db,
    create_action_point_run,
    save_action_point_item_result
)
from app.action_point_automation.models import (
    ItemExecutionResult,
    ActionClassification,
    ActionPointStatusEnum
)


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


class TestActionPointApi(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        init_db()

    def test_routes_registered_in_fastapi(self):
        registered_paths = _get_all_app_paths()
        expected_routes = [
            "/api/action-point/upload",
            "/api/action-point/run",
            "/api/action-point/stop",
            "/api/action-point/status",
            "/api/action-point/history",
            "/api/action-point/runs/{run_id}",
            "/api/action-point/runs/{run_id}/report/{report_format}"
        ]
        for route in expected_routes:
            self.assertIn(route, registered_paths, f"Route '{route}' missing from FastAPI router!")

    def test_existing_ird_and_dth_routes_preserved(self):
        registered_paths = _get_all_app_paths()
        expected_routes = [
            "/api/health",
            "/api/sites",
            "/api/settings",
            "/api/automation/start-sync",
            "/api/runs",
            "/api/dth/status",
            "/api/controller/status"
        ]
        for route in expected_routes:
            self.assertIn(route, registered_paths, f"Existing route '{route}' was removed or broken!")

    async def test_get_status_endpoint(self):
        status = await get_action_point_status()
        self.assertIn("is_running", status)
        self.assertIn("status", status)
        self.assertIn("progress_percentage", status)

    async def test_stop_endpoint(self):
        res = await stop_action_point_run()
        self.assertIn("success", res)

    async def test_history_and_details_endpoints(self):
        run_id = create_action_point_run(
            run_date="2026-10-22",
            start_time="11:00:00",
            mode="DRY_RUN",
            filename="unit_test.xlsx",
            site_id=1,
            site_name="Test Hotel",
            total_rows=1,
            action_point_rows=1
        )

        mock_item = ItemExecutionResult(
            row_number=2,
            item_code="9876",
            item_name="Butter Chicken",
            requested_category="Mains",
            requested_subcategory="Non-Veg Mains",
            original_status="Category Update",
            classification=ActionClassification.CATEGORY_UPDATE,
            status=ActionPointStatusEnum.DRY_RUN,
            failure_reason="Verified Dry Run"
        )
        save_action_point_item_result(run_id, mock_item)

        history = await list_action_point_runs(limit=10)
        self.assertTrue(len(history) > 0)
        self.assertTrue(any(r["id"] == run_id for r in history))

        details = await get_action_point_run(run_id)
        self.assertIsNotNone(details)
        self.assertEqual(details["id"], run_id)
        self.assertEqual(len(details["items"]), 1)
        self.assertEqual(details["items"][0]["item_code"], "9876")
