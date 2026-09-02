"""
Verification Test Suite — Diagnostics Tab & UI Rendering Handlers
"""
import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

def test_diagnostics_ui():
    print("======================================================================")
    print("RUNNING DIAGNOSTICS TAB & UI HANDLER VERIFICATION SUITE")
    print("======================================================================")

    from app.diagnostics.package_validator import package_validator
    from app.launcher.window_inspector import inspect_all_windows

    data_pkg = package_validator.validate_package_health()
    assert "overall_status" in data_pkg, "Missing overall_status in package health response"
    assert "checks" in data_pkg, "Missing checks in package health response"
    assert isinstance(data_pkg["checks"], list), "checks is not a list"
    assert len(data_pkg["checks"]) > 0, "checks list is empty"
    print(f"[OK] Package Health response verified (overall_status: {data_pkg['overall_status']}, checks: {len(data_pkg['checks'])}).")

    # TEST 2: Check window inspection function
    print("\n[TEST 2] Testing window inspection function...")
    data_win = inspect_all_windows()
    assert isinstance(data_win, list), "windows response is not a list"
    print(f"[OK] Windows scan response verified ({len(data_win)} windows detected).")

    # TEST 3: Verify app.js contains loadPackageHealth and scanWindows implementation
    print("\n[TEST 3] Verifying loadPackageHealth and scanWindows in app.js...")
    app_js_path = PROJECT_ROOT / "app" / "ui" / "app.js"
    with open(app_js_path, "r", encoding="utf-8") as f:
        js_code = f.read()

    assert "async function loadPackageHealth()" in js_code, "loadPackageHealth function definition missing from app.js"
    assert "async function scanWindows()" in js_code, "scanWindows function definition missing from app.js"
    assert "window.loadPackageHealth = loadPackageHealth;" in js_code, "window.loadPackageHealth assignment missing from app.js"
    assert "window.scanWindows = scanWindows;" in js_code, "window.scanWindows assignment missing from app.js"
    print("[OK] JS functions loadPackageHealth and scanWindows implemented and attached to window.")

    # TEST 4: Verify navigation handler and button bindings in app.js
    print("\n[TEST 4] Verifying navigation handler and button binding for diagnostics...")
    assert "if (tabId === 'diagnostics') safeInit('loadDiagnostics', () => { scanWindows(); loadPackageHealth(); });" in js_code
    assert "bindClick('btn-scan-windows', scanWindows);" in js_code
    print("[OK] Navigation lazy loader and btn-scan-windows click handler verified.")

    print("\n======================================================================")
    print("ALL DIAGNOSTICS TAB & UI VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("======================================================================")

if __name__ == "__main__":
    test_diagnostics_ui()
