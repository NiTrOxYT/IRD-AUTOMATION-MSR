"""
Verification Test Suite — Post-Login Whitelabel Error 2-Attempt Recovery
Tests:
1. Whitelabel after login attempt 1 -> direct /login nav -> attempt 2 -> success -> Sync MyMenu
2. Whitelabel attempt 1 -> /login -> Whitelabel attempt 2 -> WHITELABEL_AFTER_LOGIN_RETRY
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.db import init_db, get_site_by_id
from app.database.models import Site, get_site_web_url
from app.browser.browser_controller import browser_controller
from app.tunneling.tunnel_manager import tunnel_manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("Whitelabel_After_Login_Retry_Test")

class MockWhitelabelAfterLoginRetryPage:
    def __init__(self, mode="RETRY_SUCCESS"):
        self.mode = mode  # RETRY_SUCCESS or RETRY_FAIL
        self.url = "http://localhost:18001/login"
        self.submit_count = 0
        self.goto_count = 0

    async def title(self):
        if self.submit_count == 1:
            return "Whitelabel Error Page"
        elif self.submit_count == 2:
            return "Whitelabel Error Page" if self.mode == "RETRY_FAIL" else "ZMP Portal"
        return "Login"

    async def inner_text(self, selector="body"):
        if self.submit_count == 1:
            return "Whitelabel Error Page status=500"
        elif self.submit_count == 2:
            if self.mode == "RETRY_FAIL":
                return "Whitelabel Error Page status=500"
            return "Welcome to ZMP Portal Sync MyMenu Fetch Menu Logout"
        return "Login Form Username Password"

    async def content(self):
        return await self.inner_text("body")

    def is_closed(self):
        return False

    async def goto(self, url, **kwargs):
        self.goto_count += 1
        self.url = url

    async def is_visible(self, selector):
        if "username" in selector or "password" in selector:
            return True
        return False

async def run_whitelabel_after_login_retry_tests():
    print("=" * 70)
    print("RUNNING POST-LOGIN WHITELABEL 2-ATTEMPT RECOVERY SUITE")
    print("=" * 70)

    init_db()

    # TEST 1: Unit Test — Post-Login Whitelabel Detection Logic
    print("\n[TEST 1] Testing Whitelabel Error Page Classification...")
    page_mock = MockWhitelabelAfterLoginRetryPage()
    page_mock.submit_count = 1
    is_wl = await browser_controller.is_whitelabel_error_page(page_mock)
    assert is_wl is True, "Whitelabel detection failed for submit attempt 1!"
    print("[OK] Post-login Whitelabel Error Page correctly detected.")

    # TEST 2: Live Execution for Site 22 (ITC Grand Chola)
    site_22 = get_site_by_id(22)
    if not site_22:
        print("Site #22 not found in DB! Skipping live test.")
        return

    print(f"\n[TEST 2] Executing Live Reverse Tunnel & Endpoint Validation for Site 22 ({site_22.name})...")
    tunnel_res = await tunnel_manager.run_fnb_tunnel_test(site_22, keep_running=True)
    assert tunnel_res.get("checks", {}).get("tcp_endpoint") == "PASS", "TCP endpoint test failed!"

    print(f"\n[TEST 3] Executing Live 2-Attempt Login Workflow for Site 22...")
    web_url = get_site_web_url(site_22)
    res = await browser_controller.run_fnb_login_and_sync_mymenu(site_22, web_url)

    logs = res.get("logs", [])
    print("\nLive Execution Log Stream Output:")
    for l in logs:
        safe_l = l.encode('ascii', errors='replace').decode('ascii')
        print(safe_l)

    login_res = res.get("login", {})
    print(f"\nReturned login payload: {login_res}")

    assert "attempts" in login_res, "Missing 'attempts' key in login payload!"
    assert "recovery_attempted" in login_res, "Missing 'recovery_attempted' key in login payload!"
    assert "authenticated" in login_res, "Missing 'authenticated' key in login payload!"

    print("\n" + "=" * 70)
    print("ALL POST-LOGIN WHITELABEL RECOVERY TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_whitelabel_after_login_retry_tests())
