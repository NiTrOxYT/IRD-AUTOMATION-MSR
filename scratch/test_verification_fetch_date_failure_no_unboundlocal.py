"""
Dedicated Verification Suite — Fetch Date Failure & Deterministic Variable Initialization
"""
import os
import sys
import time
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.browser.browser_controller import BrowserController
from app.database.models import Site

def test_fetch_date_failure_no_unboundlocal():
    print("======================================================================", flush=True)
    print("RUNNING FETCH DATE FAILURE & VARIABLE INITIALIZATION VERIFICATION SUITE", flush=True)
    print("======================================================================", flush=True)

    bc = BrowserController()
    site = Site(id=67, name="WH Bhubaneswar", site_ip="103.243.40.46", site_port=8082, local_port=18002)

    fake_btn = AsyncMock()
    fake_btn.is_visible = AsyncMock(return_value=True)
    fake_btn.is_enabled = AsyncMock(return_value=True)
    fake_btn.click = AsyncMock(return_value=None)

    async def mock_find_element(sels, timeout_ms=5000):
        if "fetch_menu_loading" in str(sels):
            return (None, None)
        return (fake_btn, "btn-fetch")

    async def instant_sleep(secs):
        pass

    start_t = [1000.0]
    def mock_time():
        start_t[0] += 50.0
        return start_t[0]

    # Mock dependencies to simulate Fetch Menu Date Validation Failure
    with patch.object(bc, "run_fnb_login_and_sync_mymenu", new=AsyncMock(return_value={"stages": {"sync_mymenu": "PASS"}})), \
         patch("app.tunneling.tunnel_manager.tunnel_manager.run_fnb_tunnel_test", new=AsyncMock(return_value={"result_status": "REAL FNB TUNNEL — PASS", "checks": {"tcp_endpoint": "PASS"}})), \
         patch("app.database.db.record_run_history", new=MagicMock()), \
         patch("time.time", new=mock_time), \
         patch("asyncio.sleep", new=instant_sleep):

        # Mock page elements
        fake_page = AsyncMock()
        fake_page.content = AsyncMock(return_value="sync mymenu fetch menu process latest menu last received time last processing time")
        fake_page.url = "http://localhost:18002/zmp/main-menu.do"
        fake_page.inner_text = AsyncMock(return_value="last received time 2026-08-27 03:10:56.0 last processing time 2026-08-27 03:55:59.0")
        bc.page = fake_page
        bc.find_element = AsyncMock(side_effect=mock_find_element)

        # Mock _get_dashboard_time_values to return yesterday's date
        bc._get_dashboard_time_values = AsyncMock(return_value=("2026-08-27 03:10:56.0", "2026-08-27 03:55:59.0"))
        bc.is_whitelabel_error_page = AsyncMock(return_value=False)
        bc.capture_screenshot = AsyncMock(return_value=None)

        print("\n[TEST 1] Executing run_full_site_automation_sequence with stale Fetch date...", flush=True)
        res = asyncio.run(bc.run_full_site_automation_sequence(site, "http://localhost:18002"))

        print(f"Final Status: {res.get('final_status')}", flush=True)
        print(f"Failure Code: {res.get('failure_code')}", flush=True)
        print(f"Process Status: {res['sync_mymenu']['process_latest_menu']['status']}", flush=True)
        print(f"Download Status: {res['sync_mymenu']['download_action_points']['status']}", flush=True)

        # Assertions
        assert res.get("final_status") == "FAILED"
        assert res.get("failure_code") == "LAST_RECEIVED_DATE_NOT_CURRENT"
        assert res["sync_mymenu"]["fetch_menu"]["status"] == "FAILED"
        assert res["sync_mymenu"]["process_latest_menu"]["status"] == "BLOCKED"
        assert res["sync_mymenu"]["process_latest_menu"]["already_completed_today"] is False
        assert res["sync_mymenu"]["process_latest_menu"]["executed"] is False
        assert res["sync_mymenu"]["download_action_points"]["status"] == "BLOCKED"
        assert res["action_point_status"] == "BLOCKED"

        print("[OK] Fetch Date Failure handled cleanly without UnboundLocalError!", flush=True)

    print("\n======================================================================", flush=True)
    print("ALL FETCH DATE FAILURE VERIFICATION TESTS PASSED SUCCESSFULLY!", flush=True)
    print("======================================================================", flush=True)

if __name__ == "__main__":
    test_fetch_date_failure_no_unboundlocal()
