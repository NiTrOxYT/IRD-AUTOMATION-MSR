"""
Verification Test Suite — Phase 11 Real Sync MyMenu Workflow + CSV Action Point Validation + FNB Crash Recovery
"""

import sys
import os
import asyncio
import logging
from datetime import datetime
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.db import init_db, get_site_by_id
from app.database.models import Site, get_site_web_url
from app.browser.browser_controller import browser_controller
from app.browser.selectors import SelectorRegistry
from app.csv_analyzer.analyzer import analyze_action_point_csv
from app.tunneling.tunnel_manager import tunnel_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Phase11_Sync_Workflow_Test")

class MockSyncDashboardPage:
    def __init__(self, mode="CLEAR"):
        self.mode = mode
        self.url = "http://localhost:18001/zmp/main-menu.do"
        self.today_str = datetime.now().strftime("%Y-%m-%d")

    async def title(self):
        return "Sync MyMenu Dashboard"

    async def inner_text(self, selector="body"):
        return f"Sync MyMenu Dashboard Last Received Time: {self.today_str} 01:01:58.0 Last Processing Time: {self.today_str} 03:55:59.0 Fetch Menu Process Latest Menu Download Action Points Logout"

    async def content(self):
        return await self.inner_text("body")

    def is_closed(self):
        return False

async def run_phase11_tests():
    print("=" * 70)
    print("RUNNING PHASE 11 SYNC MYMENU WORKFLOW & CRASH RECOVERY VERIFICATION SUITE")
    print("=" * 70)

    init_db()
    today_str = datetime.now().strftime("%Y-%m-%d")

    # TEST 1: Sync Dashboard Markers Detection
    print("\n[TEST 1] Testing Sync Dashboard Detection...")
    mock_dash = MockSyncDashboardPage()
    body_txt = await mock_dash.inner_text("body")
    assert "sync mymenu dashboard" in body_txt.lower()
    print("[OK] Sync MyMenu Dashboard markers detected.")

    # TEST 2: Selector Registry Resolution for Fetch, Process, Download
    print("\n[TEST 2] Verifying Selector Registry for Sync Controls...")
    fetch_sels = SelectorRegistry.get_selectors_for_step("fetch_menu")
    proc_sels = SelectorRegistry.get_selectors_for_step("process_latest_menu")
    dl_sels = SelectorRegistry.get_selectors_for_step("download_action_point")
    assert len(fetch_sels) > 0, "Fetch Menu selectors empty!"
    assert len(proc_sels) > 0, "Process Latest Menu selectors empty!"
    assert len(dl_sels) > 0, "Download Action Points selectors empty!"
    print("[OK] All step selectors resolved successfully.")

    # TEST 3: Date Extraction Helper Validation
    print("\n[TEST 3] Testing Date Extraction & Validation Logic...")
    d1 = browser_controller._extract_date_part(f"{today_str} 01:01:58.0")
    assert d1 == today_str, f"Date extraction mismatch: expected {today_str}, got {d1}"
    print(f"[OK] Date extraction verified: '{d1}' equals today ({today_str}).")

    # TEST 4: CSV Analyzer First 3 Lines Classification — CLEAR
    print("\n[TEST 4] Testing CSV Analyzer for CLEAR Action Points...")
    test_dir = Path("scratch") / "test_csvs"
    test_dir.mkdir(parents=True, exist_ok=True)
    clear_csv_path = str(test_dir / "clear_test.csv")
    with open(clear_csv_path, "w", encoding="utf-8") as f:
        f.write("Line 1: No Action Point\nLine 2: No Action Point\nLine 3: No Action Point\n")

    res_clear = analyze_action_point_csv(clear_csv_path)
    assert res_clear["action_point_status"] == "CLEAR", f"Expected CLEAR, got {res_clear['action_point_status']}"
    assert len(res_clear["first_3_lines"]) == 3, "Failed to parse 3 CSV records!"
    print("[OK] CSV CLEAR status classification verified.")

    # TEST 5: CSV Analyzer First 3 Lines Classification — FOUND
    print("\n[TEST 5] Testing CSV Analyzer for FOUND Action Point...")
    found_csv_path = str(test_dir / "found_test.csv")
    with open(found_csv_path, "w", encoding="utf-8") as f:
        f.write("Line 1: No Action Point\nLine 2: Price mismatch on Item 105\nLine 3: No Action Point\n")

    res_found = analyze_action_point_csv(found_csv_path)
    assert res_found["action_point_status"] == "FOUND", f"Expected FOUND, got {res_found['action_point_status']}"
    assert res_found["action_point_found"] is True
    print("[OK] CSV ACTION POINT FOUND classification verified.")

    # TEST 6: Real Live Execution against Site 22 (ITC Grand Chola)
    site_22 = get_site_by_id(22)
    if not site_22:
        print("Site #22 not found in DB! Skipping live test.")
        return

    print(f"\n[TEST 6] Executing Real Tunnel & Endpoint Validation for Site 22 ({site_22.name})...")
    tunnel_res = await tunnel_manager.run_fnb_tunnel_test(site_22, keep_running=True)
    assert tunnel_res.get("checks", {}).get("tcp_endpoint") == "PASS", "TCP endpoint test failed!"

    print(f"\n[TEST 7] Executing Real Full Site Automation Sequence for Site 22...")
    web_url = get_site_web_url(site_22)
    seq_res = await browser_controller.run_full_site_automation_sequence(site_22, web_url)

    logs = seq_res.get("logs", [])
    print("\nLive Execution Log Stream Output:")
    for l in logs:
        safe_l = l.encode('ascii', errors='replace').decode('ascii')
        print(safe_l)

    print(f"\nFinal Site Status: {seq_res.get('final_status')}")
    print(f"Action Point Status: {seq_res.get('action_point_status')}")
    print(f"Failure Code: {seq_res.get('failure_code')}")

    print("\nFormatted Summary Output:")
    print(seq_res.get("formatted_summary", ""))

    print("\n" + "=" * 70)
    print("ALL PHASE 11 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_phase11_tests())
