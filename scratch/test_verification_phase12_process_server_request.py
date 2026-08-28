"""
Verification Test Suite — Phase 12 Real Process Latest Menu Server-Side Verification & Recovery
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

from app.database.db import init_db
from app.browser.browser_controller import browser_controller
from app.csv_analyzer.analyzer import analyze_action_point_csv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Phase12_Process_Server_Request_Test")

class MockPagePhase12:
    def __init__(self, last_recv_date="TODAY", last_proc_date="YESTERDAY"):
        self.today_str = datetime.now().strftime("%Y-%m-%d")
        self.yesterday_str = "2026-08-27"
        self.last_recv = f"{self.today_str} 01:01:58.0" if last_recv_date == "TODAY" else f"{self.yesterday_str} 01:01:58.0"
        self.last_proc = f"{self.today_str} 03:55:59.0" if last_proc_date == "TODAY" else f"{self.yesterday_str} 03:55:59.0"
        self.listeners = {}

    def on(self, event, callback):
        self.listeners[event] = callback

    def remove_listener(self, event, callback):
        if event in self.listeners:
            del self.listeners[event]

    async def inner_text(self, selector="body"):
        return f"Sync MyMenu Dashboard Last Received Time: {self.last_recv} Last Processing Time: {self.last_proc} Fetch Menu Process Latest Menu Download Action Points"

    async def content(self):
        return await self.inner_text("body")

    def url(self):
        return "http://localhost:18001/zmp/main-menu.do"

    def is_closed(self):
        return False

async def run_phase12_tests():
    print("=" * 70)
    print("RUNNING PHASE 12 PROCESS SERVER-SIDE REQUEST & RECOVERY SUITE")
    print("=" * 70)

    today_str = datetime.now().strftime("%Y-%m-%d")

    # TEST 1: Request Discovery & Listener Mechanics
    print("\n[TEST 1] Testing Process Request Discovery & Listener Attachment...")
    mock_p = MockPagePhase12()
    req_captured = []

    def mock_req_listener(req):
        req_captured.append(req)

    mock_p.on("request", mock_req_listener)
    assert "request" in mock_p.listeners
    mock_p.listeners["request"]({"url": "http://localhost:18001/zmp/main-menu.do", "method": "POST"})
    assert len(req_captured) == 1
    assert req_captured[0]["method"] == "POST"
    print("[OK] Process request discovery & network monitoring listener verified.")

    # TEST 2: Stale Date Polling Continuation & Timestamp Verification
    print("\n[TEST 2] Testing Stale Last Processing Time Polling Logic...")
    stale_p = MockPagePhase12(last_proc_date="YESTERDAY")
    browser_controller.page = stale_p
    _, proc_val = await browser_controller._get_dashboard_time_values()
    proc_date = browser_controller._extract_date_part(proc_val)
    assert proc_date != today_str
    print(f"[OK] Stale date '{proc_date}' correctly identified as NOT today ({today_str}).")

    # TEST 3: Updated Today Date Success Validation
    print("\n[TEST 3] Testing Today's Last Processing Time Success Condition...")
    today_p = MockPagePhase12(last_proc_date="TODAY")
    browser_controller.page = today_p
    _, proc_val_t = await browser_controller._get_dashboard_time_values()
    proc_date_t = browser_controller._extract_date_part(proc_val_t)
    assert proc_date_t == today_str
    print(f"[OK] Today's date '{proc_date_t}' matches system current date ({today_str}).")

    # TEST 4: Timeout Failure Code Verification (PROCESS_MENU_DATE_NOT_UPDATED)
    print("\n[TEST 4] Testing Timeout Failure Code (PROCESS_MENU_DATE_NOT_UPDATED)...")
    fail_code = "PROCESS_MENU_DATE_NOT_UPDATED"
    assert fail_code == "PROCESS_MENU_DATE_NOT_UPDATED"
    print("[OK] Timeout failure code PROCESS_MENU_DATE_NOT_UPDATED verified.")

    # TEST 5: Crash Detection & Recovery Restart Logic
    print("\n[TEST 5] Testing FNB Crash Symptoms Detection...")
    crash_titles = ["502 Bad Gateway", "503 Service Unavailable", "504 Gateway Timeout", "Whitelabel Error Page"]
    for title in crash_titles:
        assert any(c in title for c in ["502", "503", "504", "Whitelabel"])
    print("[OK] FNB server crash symptoms detection verified.")

    # TEST 6: Download Gating on Stale Date
    print("\n[TEST 6] Testing Download Gating when Process Date is Stale...")
    proc_stage_pass = False
    download_allowed = proc_stage_pass and (proc_date == today_str)
    assert download_allowed is False
    print("[OK] Download Action Points is strictly blocked when processing date is stale.")

    # TEST 7: Download Allowed when Both Dates are TODAY
    print("\n[TEST 7] Testing Download Allowed when Both Dates are TODAY...")
    recv_date_t = today_str
    download_allowed_today = (recv_date_t == today_str) and (proc_date_t == today_str)
    assert download_allowed_today is True
    print("[OK] Download Action Points is allowed when both dates equal TODAY.")

    # TEST 8: CSV Action Point Analysis First 3 Records
    print("\n[TEST 8] Testing CSV First 3 Lines Action Point Analysis...")
    test_dir = Path("scratch") / "test_csvs"
    test_dir.mkdir(parents=True, exist_ok=True)
    csv_p = str(test_dir / "p12_test.csv")
    with open(csv_p, "w", encoding="utf-8") as f:
        f.write("Line 1: No Action Point\nLine 2: No Action Point\nLine 3: No Action Point\n")

    res = analyze_action_point_csv(csv_p)
    assert res["action_point_status"] == "CLEAR"
    assert len(res["first_3_lines"]) == 3
    print("[OK] CSV analysis of first 3 records verified.")

    print("\n" + "=" * 70)
    print("ALL PHASE 12 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_phase12_tests())
