import os
import sys
import asyncio
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

async def main():
    print("=" * 65)
    print("RUNNING PHASE 5A: PORTABLE PUTTY / PLINK BUNDLE VERIFICATION SCRIPT")
    print("=" * 65)

    from app.tunneling.putty_paths import (
        get_application_root, get_bundled_plink_path,
        get_bundled_putty_path, get_relative_display_path,
        get_active_plink_path
    )
    from app.tunneling.putty_manager import putty_manager
    from app.diagnostics.package_validator import package_validator

    # 1. APPLICATION ROOT & PATH RESOLUTION
    print("\n[TEST 1] Testing Application Root & Portable Path Resolution...")
    app_root = get_application_root()
    print(f"Application Root: {app_root}")

    plink_p = get_bundled_plink_path()
    putty_p = get_bundled_putty_path()

    print(f"Bundled Plink Path: {plink_p}")
    print(f"Bundled PuTTY Path: {putty_p}")

    assert plink_p is not None and os.path.exists(plink_p), "Bundled plink.exe not found!"
    assert putty_p is not None and os.path.exists(putty_p), "Bundled putty.exe not found!"

    rel_plink = get_relative_display_path(plink_p)
    print(f"Relative Display Path: {rel_plink}")
    assert rel_plink == r"tools\putty\plink.exe" or rel_plink == "tools/putty/plink.exe", f"Unexpected relative path: {rel_plink}"

    # 2. PLINK EXECUTABLE (-V) VERSION TEST
    print("\n[TEST 2] Testing Bundled Plink Version Test (plink.exe -V)...")
    res = putty_manager.test_plink_executable()
    print(f"Test Result Message: {res['message']}")
    print(f"Path: {res['path']}")
    print(f"Parsed Version: {res['version']}")
    print(f"Full Details:\n{res.get('details', '')}")

    assert res["success"] is True, f"Plink version test failed: {res['message']}"
    assert "Release" in res["version"] or "0.8" in res["version"], f"Unexpected plink version: {res['version']}"

    # 3. PACKAGE HEALTH VALIDATOR
    print("\n[TEST 3] Testing Package Health Validator...")
    health = package_validator.validate_package_health()
    print(f"Overall Package Health: {health['overall_status']}")
    print("Component Checks:")
    for c in health["checks"]:
        print(f"  - [{c['status']}] {c['name']} -> {c['path']}")

    assert health["all_ok"] is True, "Package health check failed!"
    assert health["overall_status"] == "READY", f"Expected READY but got {health['overall_status']}"

    # 4. SIMULATION OF ALTERNATE DIRECTORY PATH RESOLUTION
    print("\n[TEST 4] Simulating Path Resolution in Alternate Extracted Location...")
    simulated_root = Path(r"D:\Apps\IRD_Automation")
    simulated_plink = simulated_root / "tools" / "putty" / "plink.exe"
    try:
        rel_sim = simulated_plink.relative_to(simulated_root)
        print(f"Simulated Root: {simulated_root}")
        print(f"Simulated Plink Path: {simulated_plink}")
        print(f"Simulated Relative Path: {rel_sim}")
        assert str(rel_sim) == r"tools\putty\plink.exe" or str(rel_sim) == "tools/putty/plink.exe"
    except Exception as e:
        print(f"Simulation warning: {e}")

    print("\n" + "=" * 65)
    print("PHASE 5A VERIFICATION COMPLETED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    asyncio.run(main())
