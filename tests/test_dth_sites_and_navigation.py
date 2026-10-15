"""
Unit and Integration Tests for DTH Automation Sites, Settings, Dashboard and Isolation
"""
import unittest
import asyncio
from unittest.mock import patch, MagicMock

from app.database.db import (
    get_all_dth_sites,
    get_dth_site_by_id,
    get_dth_site_by_name,
    add_dth_site,
    update_dth_site,
    delete_dth_site,
    get_all_dth_settings,
    set_dth_setting,
    get_dth_dashboard_metrics,
    get_all_sites
)
from app.dth_automation.router import (
    list_dth_sites,
    create_dth_site_endpoint,
    get_dth_site_endpoint,
    update_dth_site_endpoint,
    delete_dth_site_endpoint,
    toggle_dth_site_endpoint,
    test_dth_site_connectivity_endpoint as _test_connectivity_endpoint,
    open_dth_site_portal_endpoint,
    launch_dth_site_putty_endpoint,
    get_dth_settings_endpoint,
    update_dth_settings_endpoint,
    get_dth_dashboard
)
from app.dth_automation.models import DthSiteCreateRequest, DthSettingsModel
from app.dth_automation.workflow_runner import dth_workflow_runner
from fastapi import HTTPException


class TestDthSitesAndNavigation(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Record initial count of IRD sites to verify absolute isolation
        self.initial_ird_sites = get_all_sites()
        self.initial_ird_count = len(self.initial_ird_sites)

        # Clean up any leftover test site from previous runs
        leftover = get_dth_site_by_name("Test DTH Portal Isolated")
        if leftover:
            delete_dth_site(leftover["id"])
        leftover_updated = get_dth_site_by_name("Updated DTH Portal Isolated")
        if leftover_updated:
            delete_dth_site(leftover_updated["id"])

    def tearDown(self):
        leftover = get_dth_site_by_name("Test DTH Portal Isolated")
        if leftover:
            delete_dth_site(leftover["id"])
        leftover_updated = get_dth_site_by_name("Updated DTH Portal Isolated")
        if leftover_updated:
            delete_dth_site(leftover_updated["id"])

    async def test_dth_site_crud_and_isolation(self):
        """Verify DTH site CRUD works and completely preserves IRD sites without crosstalk."""
        # 1. Create a DTH site
        req = DthSiteCreateRequest(
            name="Test DTH Portal Isolated",
            portal_url="http://127.0.0.1:18099/zmp/main-menu.do",
            local_port=18099,
            remote_host="10.0.0.50",
            remote_port=80,
            idp_username="dth_admin",
            idp_password="SuperSecretPassword123!",
            notes="Isolated site for unit testing",
            enabled=True
        )

        res = await create_dth_site_endpoint(req)
        self.assertTrue(res["success"])
        site_id = res["site_id"]
        self.assertGreater(site_id, 0)

        # Verify IRD sites table was NOT modified
        ird_sites_now = get_all_sites()
        self.assertEqual(len(ird_sites_now), self.initial_ird_count, "IRD sites table count must remain strictly unchanged!")

        # 2. Retrieve DTH site list and verify password masking
        sites_list = await list_dth_sites()
        created = next((s for s in sites_list if s["id"] == site_id), None)
        self.assertIsNotNone(created)
        self.assertEqual(created["name"], "Test DTH Portal Isolated")
        # Critical security check: password must NOT be in response dict
        self.assertNotIn("idp_password", created)
        self.assertNotIn("ssh_password", created)
        self.assertNotIn("idp_password_encrypted", created)
        self.assertTrue(created["has_credentials"])

        # 3. Retrieve single site
        single_res = await get_dth_site_endpoint(site_id)
        single = single_res.get("site", single_res)
        self.assertEqual(single["name"], "Test DTH Portal Isolated")
        self.assertNotIn("idp_password", single)

        # 4. Update DTH site (preserving password when None passed)
        update_req = DthSiteCreateRequest(
            name="Updated DTH Portal Isolated",
            portal_url="http://127.0.0.1:18099/zmp/main-menu.do",
            local_port=18099,
            idp_username="dth_admin",
            idp_password=None,  # Leave blank to preserve
            notes="Updated note",
            enabled=False
        )
        up_res = await update_dth_site_endpoint(site_id, update_req)
        self.assertTrue(up_res["success"])

        updated_site = get_dth_site_by_id(site_id)
        self.assertEqual(updated_site["name"], "Updated DTH Portal Isolated")
        self.assertFalse(bool(updated_site["enabled"]))
        # Credentials must still be present in encrypted vault
        self.assertTrue(updated_site["has_credentials"])
        site_with_creds = get_dth_site_by_id(site_id, include_passwords=True)
        self.assertEqual(site_with_creds["idp_password"], "SuperSecretPassword123!")

        # 5. Toggle DTH site state
        toggle_res = await toggle_dth_site_endpoint(site_id)
        self.assertTrue(toggle_res["success"])
        self.assertTrue(toggle_res["enabled"])

        # 6. Delete DTH site
        del_res = await delete_dth_site_endpoint(site_id)
        self.assertTrue(del_res["success"])

        # Verify site is gone from DTH
        self.assertIsNone(get_dth_site_by_id(site_id))

        # Verify IRD sites table is still completely unchanged
        ird_sites_final = get_all_sites()
        self.assertEqual(len(ird_sites_final), self.initial_ird_count)

    async def test_dth_site_delete_blocked_when_active(self):
        """Verify DTH site deletion is blocked with HTTP 409 if active run references it."""
        site_id = add_dth_site({
            "name": "Active Run Site",
            "local_port": 18098,
            "idp_username": "admin"
        })

        try:
            # Simulate active run referencing site_id
            with patch.object(dth_workflow_runner, "is_running", True), \
                 patch.object(dth_workflow_runner, "current_site_id", site_id):
                with self.assertRaises(HTTPException) as ctx:
                    await delete_dth_site_endpoint(site_id)
                self.assertEqual(ctx.exception.status_code, 409)
                self.assertIn("active", ctx.exception.detail.lower())
        finally:
            # Clean up after test
            delete_dth_site(site_id)

    async def test_dth_site_connectivity_check(self):
        """Test DTH site connectivity test endpoint with socket mock."""
        site_id = add_dth_site({
            "name": "Connectivity Test Site",
            "portal_url": "http://127.0.0.1:18097/zmp/main-menu.do",
            "local_port": 18097
        })

        try:
            with patch("app.dth_automation.router._check_connectivity", return_value={"success": True, "message": "Port 18097 is reachable."}):
                res = await _test_connectivity_endpoint(site_id)
                self.assertTrue(res["success"])
        finally:
            delete_dth_site(site_id)

    async def test_dth_settings_crud(self):
        """Test DTH-specific settings update and retrieval."""
        res = await get_dth_settings_endpoint()
        self.assertTrue(res["success"])
        current_settings = res["settings"]
        self.assertIn("default_mode", current_settings)
        self.assertIn("channel_delay_seconds", current_settings)

        # Update settings with valid data
        new_settings = {
            "default_mode": "DRY_RUN",
            "channel_delay_seconds": "2.5",
            "max_row_count": "3000",
            "max_file_size_mb": "15",
            "page_load_timeout": "75",
            "save_timeout": "45",
            "image_allowed_extensions": ".png, .jpg",
            "max_image_size_kb": "1024",
            "headless": "true",
            "browser_type": "msedge",
            "log_level": "DEBUG",
            "debug_screenshots": "false"
        }

        up_res = await update_dth_settings_endpoint(new_settings)
        self.assertTrue(up_res["success"])

        # Verify retrieved settings match
        get_res = await get_dth_settings_endpoint()
        updated = get_res["settings"]
        self.assertEqual(updated["channel_delay_seconds"], "2.5")
        self.assertEqual(updated["max_row_count"], "3000")
        self.assertEqual(updated["page_load_timeout"], "75")
        self.assertEqual(updated["headless"], "true")
        self.assertEqual(updated["browser_type"], "msedge")
        self.assertEqual(updated["log_level"], "DEBUG")
        self.assertEqual(updated["debug_screenshots"], "false")

        # Restore defaults
        set_dth_setting("channel_delay_seconds", "1.0")
        set_dth_setting("max_row_count", "5000")
        set_dth_setting("headless", "false")
        set_dth_setting("browser_type", "chromium")
        set_dth_setting("log_level", "INFO")
        set_dth_setting("debug_screenshots", "true")

    async def test_dth_dashboard_stats(self):
        """Test DTH dashboard statistics calculation."""
        res = await get_dth_dashboard()
        self.assertTrue(res["success"])
        self.assertIn("metrics", res)
        self.assertIn("recent_runs", res)
        self.assertIn("sites", res)
        self.assertIn("execution", res)
        self.assertIn("active_run", res)
        metrics = res["metrics"]
        self.assertIn("total_sites", metrics)
        self.assertIn("total_channels_processed", metrics)
        self.assertIn("successful_channels", metrics)
        self.assertIn("skipped_duplicates", metrics)
        self.assertIn("failed_channels", metrics)
        self.assertIn("total_runs", metrics)

    async def test_dth_open_portal_and_launch_putty(self):
        """Test open-portal and launch-putty endpoints for DTH sites."""
        site_id = add_dth_site({
            "name": "PuTTY & Portal Test Site",
            "site_ip": "127.0.0.1",
            "site_port": 8080,
            "local_port": 18123,
            "portal_url": "http://localhost:18123/zmp/main-menu.do",
            "enabled": True
        })

        try:
            with patch("webbrowser.open") as mock_browser:
                res = await open_dth_site_portal_endpoint(site_id)
                self.assertTrue(res["success"])
                self.assertIn("18123", res["portal_url"])
                mock_browser.assert_called_once()

            with patch("app.tunneling.putty_manager.putty_manager.launch_putty_gui", return_value=(True, "PuTTY GUI launched successfully")) as mock_putty:
                putty_res = await launch_dth_site_putty_endpoint(site_id)
                self.assertTrue(putty_res["success"])
                mock_putty.assert_called_once()
        finally:
            delete_dth_site(site_id)

