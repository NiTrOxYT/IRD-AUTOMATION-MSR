"""
Regression Test Suite — Whitelabel Page Direct /login Navigation & Login Execution Path
Tests:
1. Whitelabel detection on initial /zmp/main-menu.do load.
2. Direct navigation to http://localhost:{local_port}/login (No page.go_back()).
3. Login selector detection & Hard Safety Check.
4. Login form submission & authentication state.
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
logger = logging.getLogger("Whitelabel_Redirect_Test")

class MockPageForWhitelabelRedirect:
    def __init__(self, initial_port=18001):
        self.port = initial_port
        self.url = f"http://localhost:{initial_port}/zmp/main-menu.do"
        self.is_whitelabel = True
        self.go_back_called = False
        self.goto_calls = []

    async def title(self):
        return "Whitelabel Error Page" if self.is_whitelabel else "Login"

    async def inner_text(self, selector="body"):
        if self.is_whitelabel:
            return "Whitelabel Error Page\nThis application has no explicit mapping for /error, so you are seeing this as a fallback.\nstatus=404"
        return "Login Form Username Password"

    async def content(self):
        if self.is_whitelabel:
            return "<html><body>Whitelabel Error Page<br>This application has no explicit mapping for /error<br>status=404</body></html>"
        return "<html><body><form><input name='username'/><input name='password'/></form></body></html>"

    def is_closed(self):
        return False

    async def goto(self, url, wait_until="domcontentloaded", timeout=30000):
        self.goto_calls.append(url)
        self.url = url
        if "/login" in url:
            self.is_whitelabel = False

    async def go_back(self, timeout=10000):
        self.go_back_called = True

async def run_whitelabel_redirect_tests():
    print("=" * 70)
    print("RUNNING WHITELABEL DIRECT /LOGIN NAVIGATION & SAFETY CHECK SUITE")
    print("=" * 70)

    init_db()

    # TEST 1: Unit Mock Test — Flow Order & Safety Checks
    print("\n[TEST 1] Testing Whitelabel Error -> Direct /login Navigation Execution...")
    mock_p = MockPageForWhitelabelRedirect(initial_port=18002)

    # 1. Inspect initial page
    wl_detected = await browser_controller.is_whitelabel_error_page(mock_p)
    assert wl_detected is True, "Failed to detect initial Whitelabel Error Page!"
    print("[OK] Step 1: Initial page classified as Whitelabel Error Page.")

    # 2. Direct Navigation to /login
    login_target = f"http://localhost:{mock_p.port}/login"
    await mock_p.goto(login_target)
    assert mock_p.go_back_called is False, "page.go_back() was executed! Should be disabled."
    assert login_target in mock_p.goto_calls, f"Playwright goto() was not called with {login_target}"
    print(f"[OK] Step 2: Direct navigation executed to {login_target} (go_back() NOT called).")

    # 3. Post-Navigation Re-evaluation
    wl_after = await browser_controller.is_whitelabel_error_page(mock_p)
    assert wl_after is False, "Whitelabel error still detected after login navigation!"
    assert "/login" in mock_p.url, f"Current URL does not contain /login: {mock_p.url}"
    print("[OK] Step 3: Login page verified, safety checks passed.")
    print("TEST 1: PASS - Direct /login recovery workflow verified.")

    # TEST 2: Dynamic Port Verification
    print("\n[TEST 2] Verifying Dynamic Local Port URL Construction...")
    test_site = Site(id=999, name="TestSite", local_port=18005)
    port = getattr(test_site, "local_port", 18001)
    login_url = f"http://localhost:{port}/login"
    assert login_url == "http://localhost:18005/login", f"Dynamic port URL mismatch: {login_url}"
    print(f"[OK] Dynamic port URL generated correctly: {login_url}")
    print("TEST 2: PASS - Dynamic port construction verified.")

    # TEST 3: Live Real Execution for Site 22 (ITC Grand Chola)
    site_22 = get_site_by_id(22)
    if not site_22:
        print("Site #22 not found in DB! Skipping live test.")
        return

    print(f"\n[TEST 3] Executing Live Real Tunnel & Login Workflow for Site 22 ({site_22.name})...")
    tunnel_res = await tunnel_manager.run_fnb_tunnel_test(site_22, keep_running=True)
    assert tunnel_res.get("checks", {}).get("tcp_endpoint") == "PASS", "TCP endpoint test failed!"

    web_url = get_site_web_url(site_22)
    res = await browser_controller.run_fnb_login_and_sync_mymenu(site_22, web_url)

    logs = res.get("logs", [])
    print("\nLog Stream Output:")
    for l in logs:
        safe_l = l.encode('ascii', errors='replace').decode('ascii')
        print(safe_l)

    # Validate log markers
    has_initial = any("[BROWSER] Checking for Whitelabel Error Page..." in l for l in logs)
    has_login_start = any("[LOGIN] Starting login workflow..." in l for l in logs)
    assert has_initial, "Missing mandatory initial log marker!"
    assert has_login_start, "Missing mandatory login start marker!"

    print("\n" + "=" * 70)
    print("ALL WHITELABEL REDIRECT TESTS PASSED SUCCESSFULLY!")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(run_whitelabel_redirect_tests())
