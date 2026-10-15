import os
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from app.database.db import init_db, get_all_sites, get_dth_run_details
from app.dth_automation.models import DthExecutionMode, DthRunState, DthItemState
from app.dth_automation.workflow_runner import DthWorkflowRunner
from app.dth_automation.audit_logger import sanitize_message
from app.dth_automation.report_generator import export_dth_reports


class TestDthWorkflowAndReports(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        init_db()
        self.sites = get_all_sites()
        self.site_id = self.sites[0].id if self.sites else 1

        self.temp_dir = tempfile.TemporaryDirectory()
        self.test_dir = Path(self.temp_dir.name)

        # Create test CSV
        self.test_csv = self.test_dir / "channels.csv"
        self.test_csv.write_text(
            "channel_number,name,osd,image,categories\n"
            "101,DD National,DD National,dd.png,\"all, News\"\n"
            "102,Star Sports,Star Sports,star.png,\"Sports\"\n",
            encoding="utf-8"
        )

        # Create dummy image files
        (self.test_dir / "dd.png").write_bytes(b"dummy")
        (self.test_dir / "star.png").write_bytes(b"dummy")

        self.runner = DthWorkflowRunner()

    async def asyncTearDown(self):
        self.temp_dir.cleanup()

    def test_audit_logger_sanitization(self):
        msg = "User logged in with password='SuperSecretPassword123' and bearer 983247923847"
        sanitized = sanitize_message(msg)
        self.assertNotIn("SuperSecretPassword123", sanitized)
        self.assertNotIn("983247923847", sanitized)
        self.assertIn("***REDACTED***", sanitized)

    async def test_live_mode_requires_authorization(self):
        with self.assertRaises(ValueError):
            await self.runner.execute_batch(
                file_path=str(self.test_csv),
                image_dir=str(self.test_dir),
                site_id=self.site_id,
                mode=DthExecutionMode.LIVE,
                authorized=False
            )

    async def test_dry_run_execution(self):
        # In dry run, zero portal mutations happen
        res = await self.runner.execute_batch(
            file_path=str(self.test_csv),
            image_dir=str(self.test_dir),
            site_id=self.site_id,
            mode=DthExecutionMode.DRY_RUN,
            authorized=False
        )
        self.assertTrue(res["success"])
        run_id = res["run_id"]
        self.assertIsNotNone(run_id)

        # Verify DB details
        details = get_dth_run_details(run_id)
        self.assertIsNotNone(details)
        self.assertEqual(details["run"]["mode"], "DRY_RUN")
        self.assertEqual(details["run"]["total_channels"], 2)
        self.assertEqual(len(details["channels"]), 2)
        self.assertEqual(details["channels"][0]["status"], "READY")

        # Verify reports generated
        self.assertIn("reports", res)
        self.assertTrue(os.path.exists(res["reports"]["csv_path"]))
        self.assertTrue(os.path.exists(res["reports"]["json_path"]))

    def test_report_export_format(self):
        summary = {
            "id": 999,
            "run_date": "2026-10-13",
            "mode": "DRY_RUN",
            "status": "COMPLETED",
            "total_channels": 1,
            "successful_channels": 1
        }
        channels = [
            {
                "row_number": 2,
                "channel_number": "101",
                "name": "DD National",
                "osd": "DD National",
                "categories": ["all", "News"],
                "status": "READY",
                "verified_in_portal": False,
                "duration_seconds": 0.5,
                "error_reason": "Dry run preview"
            }
        ]
        paths = export_dth_reports(summary, channels)
        self.assertTrue(os.path.exists(paths["csv_path"]))
        self.assertTrue(os.path.exists(paths["json_path"]))

        with open(paths["json_path"], "r", encoding="utf-8") as jf:
            data = json.load(jf)
            self.assertEqual(data["summary"]["id"], 999)
            self.assertEqual(len(data["channels"]), 1)

    async def test_workflow_runner_honors_headless_setting(self):
        from app.database.db import set_dth_setting
        set_dth_setting("headless", "true")
        set_dth_setting("browser_type", "chromium")

        with patch("app.dth_automation.workflow_runner.DthPortalController") as MockPC:
            mock_inst = MagicMock()
            mock_inst.initialize = unittest.mock.AsyncMock()
            mock_inst.navigate_to_url = unittest.mock.AsyncMock(return_value=True)
            mock_inst.login_if_required = unittest.mock.AsyncMock()
            mock_inst.open_dth_configuration = unittest.mock.AsyncMock()
            mock_inst.read_available_categories = unittest.mock.AsyncMock(return_value=["all"])
            mock_inst.get_existing_channels_from_portal = unittest.mock.AsyncMock(return_value=(set(), set()))
            mock_inst.existing_channels_map = {}
            mock_inst.close = unittest.mock.AsyncMock()
            MockPC.return_value = mock_inst

            await self.runner.execute_batch(
                file_path=str(self.test_csv),
                image_dir=str(self.test_dir),
                site_id=self.site_id,
                mode=DthExecutionMode.DRY_RUN,
                authorized=False
            )
            mock_inst.initialize.assert_awaited_once_with(headless=True, browser_type_str="chromium")

        # Verify headless=False
        set_dth_setting("headless", "false")
        with patch("app.dth_automation.workflow_runner.DthPortalController") as MockPC:
            mock_inst = MagicMock()
            mock_inst.initialize = unittest.mock.AsyncMock()
            mock_inst.navigate_to_url = unittest.mock.AsyncMock(return_value=True)
            mock_inst.login_if_required = unittest.mock.AsyncMock()
            mock_inst.open_dth_configuration = unittest.mock.AsyncMock()
            mock_inst.read_available_categories = unittest.mock.AsyncMock(return_value=["all"])
            mock_inst.get_existing_channels_from_portal = unittest.mock.AsyncMock(return_value=(set(), set()))
            mock_inst.existing_channels_map = {}
            mock_inst.close = unittest.mock.AsyncMock()
            MockPC.return_value = mock_inst

            await self.runner.execute_batch(
                file_path=str(self.test_csv),
                image_dir=str(self.test_dir),
                site_id=self.site_id,
                mode=DthExecutionMode.DRY_RUN,
                authorized=False
            )
            mock_inst.initialize.assert_awaited_once_with(headless=False, browser_type_str="chromium")


if __name__ == "__main__":
    unittest.main()
