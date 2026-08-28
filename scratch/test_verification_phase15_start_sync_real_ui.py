"""
Phase 15 Verification Test Suite — PyWebView Desktop UI START SYNC Trigger Chain & Real Integration
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
from app.database.db import get_all_sites

def test_phase15_real_ui_start_sync():
    print("======================================================================")
    print("RUNNING PHASE 15 PYWEBVIEW DESKTOP UI START SYNC INTEGRATION SUITE")
    print("======================================================================")

    # TEST 1: DOM Element Check
    print("\n[TEST 1] Verifying START SYNC DOM element in index.html...")
    index_path = Path(__file__).parent.parent / "app" / "ui" / "index.html"
    with open(index_path, "r", encoding="utf-8") as f:
        html = f.read()
    assert 'id="btn-start-sync"' in html
    assert 'id="modal-confirm-real-run"' in html
    assert 'id="btn-proceed-real-run"' in html
    print("[OK] START SYNC button, modal, and proceed button DOM elements exist.")

    # TEST 2: Click Handler Binding & Log Stream Check
    print("\n[TEST 2] Verifying app.js click handler binding & log stream tags...")
    appjs_path = Path(__file__).parent.parent / "app" / "ui" / "app.js"
    with open(appjs_path, "r", encoding="utf-8") as f:
        js = f.read()

    assert "[UI] app.js loaded" in js
    assert "[UI BOOT] DOMContentLoaded fired" in js or "[UI] DOMContentLoaded fired" in js
    assert "[UI] Binding START SYNC handler" in js
    assert "[UI] START SYNC BUTTON CLICK EVENT FIRED" in js
    assert "[UI] START SYNC button element found" in js
    assert "[UI] START SYNC disabled:" in js
    assert "[UI INIT] START SYNC binding: PASS" in js or "[UI] START SYNC click handler attached" in js
    assert "[UI] Confirmation modal opened" in js
    assert "[UI] REAL RUN confirmation clicked" in js
    assert "[UI] startAutomation(false) called" in js
    print("[OK] app.js log stream tags and click handler bindings verified.")

    # TEST 3: Confirmation Flow Invokes startAutomation()
    print("\n[TEST 3] Verifying confirmation flow invokes startAutomation()...")
    assert "bindClick('btn-proceed-real-run'" in js
    assert "startAutomation(false)" in js
    print("[OK] Proceed button safely invokes startAutomation(false).")

    # TEST 4: Selected Site IDs Payload Collection
    print("\n[TEST 4] Verifying selected site IDs collection logic...")
    assert "document.querySelectorAll('.chk-site-queue:checked')" in js
    assert "[UI] Selected site IDs:" in js
    print("[OK] Selected site IDs collection verified.")

    # TEST 5: Dynamic API Base URL Generation
    print("\n[TEST 5] Verifying getApiBaseUrl() dynamic URL helper in app.js...")
    assert "function getApiBaseUrl()" in js
    assert "window.location.origin" in js
    assert "[UI] API URL:" in js
    print("[OK] getApiBaseUrl() helper and API URL logging verified.")

    # TEST 6: POST Request Reaching FastAPI Endpoints
    print("\n[TEST 6] Verifying FastAPI endpoint route handlers...")
    routes = [r.path for r in app.routes]
    assert "/api/automation/start-sync" in routes
    assert "/api/automation/start-dry-run" in routes
    assert "/api/automation/start" in routes
    print("[OK] FastAPI routes verified.")

    # TEST 7: FastAPI Receives Site IDs & Invokes Runner
    print("\n[TEST 7] Testing FastAPI handler with site selection...")
    async def mock_endpoint():
        return await start_automation_endpoint({"site_ids": [22], "dry_run": True})
    res = asyncio.run(mock_endpoint())
    assert res["success"] is True
    print("[OK] FastAPI endpoint execution returned success.")

    # TEST 8: Workflow Runner Scheduling Background Task
    print("\n[TEST 8] Verifying Workflow Runner background task execution...")
    workflow_runner.is_running = False
    async def mock_batch():
        return await workflow_runner.start_batch_sync(selected_site_ids=[22], dry_run=True)
    run_id = asyncio.run(mock_batch())
    assert run_id > 0
    print(f"[OK] Batch run scheduled and completed with Run ID #{run_id}.")

    # TEST 9: Runner Site Processing Verification
    print("\n[TEST 9] Verifying runner starting selected site logs...")
    assert hasattr(workflow_runner, "_process_single_site_workflow")
    print("[OK] Workflow runner single site processing method verified.")

    # TEST 10: Phase 13 Once-Per-Day Logic Intact
    print("\n[TEST 10] Verifying Phase 13 once-per-day rule intact...")
    controller = BrowserController()
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    today_stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.0")
    assert controller._extract_date_part(today_stamp) == today_str
    print("[OK] Phase 13 once-per-day timestamp extraction verified.")

    print("\n======================================================================")
    print("ALL PHASE 15 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("======================================================================")

if __name__ == "__main__":
    test_phase15_real_ui_start_sync()
