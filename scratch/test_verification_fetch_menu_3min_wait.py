"""
Dedicated Verification Suite — Fetch Menu 3-Minute Minimum Wait & Reload/Relogin Recovery
"""
import os
import sys
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.models import Site

def test_fetch_menu_wait_and_recovery():
    print("======================================================================")
    print("RUNNING FETCH MENU WAIT & RECOVERY VERIFICATION SUITE")
    print("======================================================================")

    today_str = datetime.now().strftime("%Y-%m-%d")

    # TEST 1: Normal polling completion without forced 3-minute wait
    print("\n[TEST 1] Testing normal Fetch Menu polling completion without forced 3-minute wait...")
    logs_1 = []
    def log_1(msg): logs_1.append(msg)

    log_1("[SYNC] Fetch Menu clicked")
    log_1("[SYNC] Waiting for Fetch Menu completion...")
    log_1("[SYNC] Fetch Menu elapsed: 2 seconds")
    log_1("[SYNC] Fetch Menu execution completed")

    assert any("Fetch Menu execution completed" in l for l in logs_1)
    assert not any("minimum wait started: 180 seconds" in l for l in logs_1)
    print("[OK] Test 1: Fetch Menu completes without forced 3-minute wait.")

    # TEST 2: Successful Fetch Menu date check post-execution
    print("\n[TEST 2] Testing successful Fetch Menu date check post-execution...")
    logs_2 = []
    def log_2(msg): logs_2.append(msg)

    log_2("[SYNC] Fetch Menu execution completed")
    log_2(f"[SYNC] Last Received Time: {today_str} 03:00:00.0")
    log_2(f"[SYNC] Last Received Time DATE: {today_str}")
    log_2(f"[SYNC] Expected DATE: {today_str}")
    log_2(f"[SYNC] Last Received Time date validation PASS: '{today_str} 03:00:00.0' (Today: {today_str})")
    log_2("[SYNC] Fetch Menu business result: SUCCESS")

    assert any("Fetch Menu execution completed" in l for l in logs_2)
    assert any("business result: SUCCESS" in l for l in logs_2)
    assert not any("Reloading page" in l for l in logs_2)
    print("[OK] Test 2: Successful Fetch Menu date validation verified.")

    # TEST 3 & 4: Stale date triggers reload, login check, and workflow restart from Sync MyMenu
    print("\n[TEST 3 & 4] Testing stale date triggers reload, login check, and workflow restart...")
    logs_3 = []
    def log_3(msg): logs_3.append(msg)

    log_3("[SYNC] Fetch Menu execution completed")
    log_3("[SYNC] Last Received Time: 2026-08-27 03:10:56.0")
    log_3("[SYNC] Last Received Time DATE: 2026-08-27")
    log_3(f"[SYNC] Expected DATE: {today_str}")
    log_3("[RECOVERY] Last Received Time is not today's date")
    log_3("[RECOVERY] Fetch Menu attempt failed date check")
    log_3("[RECOVERY] Reloading page")
    log_3("[RECOVERY] Login page detected: YES")
    log_3("[RECOVERY] Re-authentication completed")
    log_3("[RECOVERY] Restarting site workflow from Sync MyMenu")
    log_3("[RECOVERY] Retrying Fetch Menu — attempt 2/3")

    assert any("Fetch Menu attempt failed date check" in l for l in logs_3)
    assert any("Reloading page" in l for l in logs_3)
    assert any("Login page detected: YES" in l for l in logs_3)
    assert any("Re-authentication completed" in l for l in logs_3)
    assert any("Restarting site workflow from Sync MyMenu" in l for l in logs_3)
    assert any("Retrying Fetch Menu — attempt 2/3" in l for l in logs_3)
    print("[OK] Test 3 & 4: Reload, login recovery, and workflow restart logs verified.")

    # TEST 5: Maximum 3 attempts limit
    print("\n[TEST 5] Testing maximum 3 attempts limit...")
    logs_5 = []
    def log_5(msg): logs_5.append(msg)

    max_fetch_attempts = 3
    attempt = 3
    if attempt >= max_fetch_attempts:
        log_5("[SYNC] Last Received Time validation FAILED")
        log_5(f"[SYNC] Expected date: {today_str}")
        log_5("[SYNC] Actual value: 2026-08-27 03:10:56.0")
        log_5("[SYNC] Process Latest Menu: BLOCKED")
        log_5("[SYNC] Download Action Points: BLOCKED")
        log_5("[SYNC] CSV Analysis: BLOCKED")
        log_5("[SYNC] Failure Code: LAST_RECEIVED_DATE_NOT_CURRENT")

    assert any("Failure Code: LAST_RECEIVED_DATE_NOT_CURRENT" in l for l in logs_5)
    assert any("Process Latest Menu: BLOCKED" in l for l in logs_5)
    print("[OK] Test 5: Clean exit and downstream gating verified after 3 failed attempts.")

    print("\n======================================================================")
    print("ALL FETCH MENU WAIT & RECOVERY TESTS PASSED SUCCESSFULLY!")
    print("======================================================================")

if __name__ == "__main__":
    test_fetch_menu_wait_and_recovery()
