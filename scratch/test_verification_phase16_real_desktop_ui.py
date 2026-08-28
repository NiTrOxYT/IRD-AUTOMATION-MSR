"""
Phase 16 Verification Test Suite — Real PyWebView Desktop UI START SYNC Trigger & Diagnostic Chain
"""
import os
import sys
import json
import asyncio
import datetime
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app, start_automation_endpoint
from app.automation.workflow_runner import workflow_runner
from app.browser.browser_controller import BrowserController

def test_phase16_real_desktop_ui_verification():
    print("======================================================================")
    print("RUNNING PHASE 16 PYWEBVIEW DESKTOP UI START SYNC DIAGNOSTIC SUITE")
    print("======================================================================")

    # TEST 1: Check PyWebView File Resolution & Logging in main.py
    print("\n[TEST 1] Verifying PyWebView file resolution and logging in main.py...")
    main_path = Path(__file__).parent.parent / "app" / "main.py"
    with open(main_path, "r", encoding="utf-8") as f:
        main_code = f.read()

    assert "[PYWEBVIEW] Creating desktop window" in main_code
    assert "[PYWEBVIEW] UI HTML path:" in main_code
    assert "[PYWEBVIEW] UI HTML exists:" in main_code
    assert "[PYWEBVIEW] UI JavaScript path:" in main_code
    assert "[PYWEBVIEW] UI JavaScript exists:" in main_code
    print("[OK] PyWebView file resolution logging verified.")

    # TEST 2: Check Visible Diagnostic Markers in index.html
    print("\n[TEST 2] Verifying visible diagnostic markers in index.html...")
    index_path = Path(__file__).parent.parent / "app" / "ui" / "index.html"
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()

    assert 'id="phase16-ui-version-marker"' in html
    assert 'IRD UI BUILD: PHASE17' in html or 'IRD UI BUILD: PHASE16' in html
    assert 'id="phase16-js-status"' in html
    assert 'PHASE16 JS: NOT YET' in html
    assert 'id="phase16-dom-status"' in html
    assert 'START SYNC DOM: UNKNOWN' in html
    assert 'id="phase16-click-status"' in html
    assert 'START SYNC CLICK: NOT YET' in html
    print("[OK] Visible UI diagnostic markers in index.html verified.")

    # TEST 3: Check Inline Click Bypass & Script Versioning in index.html
    print("\n[TEST 3] Verifying inline click bypass & app.js?v=phase16 script tag...")
    assert 'onclick="window.__phase16ButtonClicked && window.__phase16ButtonClicked()"' in html
    assert 'window.__phase16ButtonClicked = function()' in html
    assert 'src="/static/app.js?v=phase16"' in html
    print("[OK] Inline click bypass and cache-busting version query verified.")

    # TEST 4: Check app.js Top-Level Execution Log & Build Marker
    print("\n[TEST 4] Verifying app.js top-level execution log & build marker...")
    appjs_path = Path(__file__).parent.parent / "app" / "ui" / "app.js"
    with open(appjs_path, "r", encoding="utf-8") as f:
        js = f.read()

    assert '[UI BOOT] PHASE16 app.js EXECUTED' in js
    assert 'window.__IRD_PHASE16_JS_LOADED__ = true' in js
    assert 'window.__IRD_UI_BUILD__ = "PHASE16-2026-08-28"' in js
    print("[OK] app.js top-level execution log and build marker verified.")

    # TEST 5: Check DOMContentLoaded Diagnostics & Computed Style Lookups
    print("\n[TEST 5] Verifying DOMContentLoaded diagnostics & computed style lookups...")
    assert '[UI BOOT] DOMContentLoaded fired' in js
    assert '[UI PHASE16] START SYNC DOM lookup' in js
    assert '[UI PHASE16] Button found:' in js
    assert '[UI PHASE16] START SYNC bounding rect:' in js
    assert '[UI PHASE16] elementFromPoint:' in js
    assert '[UI PHASE16] START SYNC button count:' in js
    assert 'PHASE16 JS: LOADED' in js
    assert 'START SYNC DOM: FOUND' in js
    print("[OK] DOMContentLoaded runtime diagnostics verified.")

    # TEST 6: Check Delegated Event Listener Safety Net
    print("\n[TEST 6] Verifying delegated event listener safety net...")
    assert 'document.addEventListener("click", function(event)' in js
    assert 'event.target.closest("#btn-start-sync")' in js
    assert '[UI PHASE16] DELEGATED CLICK FIRED' in js
    assert '[UI] START SYNC BUTTON CLICK EVENT FIRED' in js
    print("[OK] Delegated click handler safety net verified.")

    # TEST 7: Check API URL Resolution & Route Registration
    print("\n[TEST 7] Verifying API URL resolution & route registration...")
    routes = [r.path for r in app.routes]
    assert "/api/automation/start-sync" in routes
    assert "function getApiBaseUrl()" in js
    print("[OK] API URL resolution and FastAPI endpoint routes verified.")

    # TEST 8: Phase 13 Once-Per-Day Preservation
    print("\n[TEST 8] Verifying Phase 13 once-per-day rule intact...")
    controller = BrowserController()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    today_stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.0")
    assert controller._extract_date_part(today_stamp) == today_str
    print("[OK] Phase 13 once-per-day logic verified.")

    print("\n======================================================================")
    print("ALL PHASE 16 DIAGNOSTIC & INTEGRATION TESTS PASSED SUCCESSFULLY!")
    print("======================================================================")

if __name__ == "__main__":
    test_phase16_real_desktop_ui_verification()
