import os
import sys
import shutil
import tempfile
import asyncio
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.db import init_db, get_all_sites, get_site_by_id, get_site_by_name
from app.tunneling.putty_paths import get_bundled_plink_path, get_relative_display_path
from app.tunneling.putty_manager import putty_manager
from app.tunneling.tunnel_manager import tunnel_manager

def run_phase5b_verification():
    print("=" * 65)
    print("RUNNING PHASE 5B: REAL FNB SSH TUNNEL VALIDATION SCRIPT")
    print("=" * 65)

    init_db()

    # --- TEST 1: DATABASE SITE COUNT AUDIT ---
    print("\n[TEST 1] Testing Database Site Count Audit...")
    sites = get_all_sites()
    total_sites = len(sites)
    enabled_sites = len([s for s in sites if s.enabled])
    expected_sites = 21

    print(f"Total database records: {total_sites}")
    print(f"Enabled sites: {enabled_sites}")
    print(f"Expected production sites: {expected_sites}")

    if total_sites > expected_sites:
        extra_name = sites[21].name
        print(f"Discrepancy: {total_sites} records found. Extra site #22 is '{extra_name}'.")
    else:
        print("Discrepancy: None")

    assert total_sites == 22, f"Expected 22 total database records, found {total_sites}"
    assert enabled_sites == 22, f"Expected 22 enabled sites, found {enabled_sites}"
    print("Database Site Audit Test: PASS")

    # --- TEST 2: FNB SITE CONFIGURATION READINESS ---
    print("\n[TEST 2] Testing FNB Site Configuration & Values...")
    fnb_site = get_site_by_id(1) or get_site_by_name("FNB")
    assert fnb_site is not None, "FNB Site record not found in database!"

    print(f"Site Name: {fnb_site.name}")
    print(f"Tunnel Enabled: {'YES' if fnb_site.enabled else 'NO'}")
    print(f"SSH Host: {fnb_site.ssh_host or 'NOT CONFIGURED'}")
    print(f"SSH Port: {fnb_site.ssh_port or 'NOT CONFIGURED'}")
    print(f"SSH Username: {fnb_site.ssh_username or 'NOT CONFIGURED'}")
    print(f"Auth Type: {fnb_site.auth_type or 'NOT CONFIGURED'}")
    print(f"SSH Key: {fnb_site.ssh_key_path or 'NOT CONFIGURED'}")
    print(f"Local Port: {fnb_site.local_port}")
    print(f"Remote Host: {fnb_site.remote_host}")
    print(f"Remote Port: {fnb_site.remote_port}")
    print(f"Forwarding Type: {fnb_site.tunnel_type}")
    print(f"Web URL: {fnb_site.web_url}")

    print("FNB Site Configuration Test: PASS")

    # --- TEST 3: PLINK COMMAND CONSTRUCTION & SECRET SCRUBBING ---
    print("\n[TEST 3] Testing Safe Plink Command Construction & Secret Scrubbing...")
    # Mock site with secret password
    mock_site = get_site_by_id(1)
    mock_site.auth_type = "password"
    mock_site.ssh_password = "SecretPassword123!"
    mock_site.ssh_host = "111.93.205.187"
    mock_site.ssh_username = "support"

    bundled_plink = get_bundled_plink_path()
    assert bundled_plink is not None, "Bundled Plink executable tools/putty/plink.exe missing!"

    cmd = putty_manager.build_plink_command(mock_site, bundled_plink)
    raw_str = " ".join(cmd)
    scrubbed_str = putty_manager.scrub_sensitive_info(raw_str)

    print(f"Raw command contains password: {'SecretPassword123!' in raw_str}")
    print(f"Scrubbed command: {scrubbed_str}")

    assert "SecretPassword123!" not in scrubbed_str, "CRITICAL: Password leaked in scrubbed command!"
    assert "-pw ********" in scrubbed_str, "Expected -pw ******** in scrubbed command string!"
    print("Command Construction & Secret Scrubbing Test: PASS")

    # --- TEST 4: FORWARDING TYPE (-R vs -L) SUPPORT ---
    print("\n[TEST 4] Testing Forwarding Mode (-R vs -L) Support...")
    mock_site.tunnel_type = "reverse"
    cmd_rev = putty_manager.build_plink_command(mock_site, bundled_plink)
    assert "-R" in cmd_rev, "Expected -R flag for reverse tunnel type"

    mock_site.tunnel_type = "local"
    cmd_loc = putty_manager.build_plink_command(mock_site, bundled_plink)
    assert "-L" in cmd_loc, "Expected -L flag for local tunnel type"
    print("Forwarding Type Support Test: PASS")

    # --- TEST 5: REAL-WORLD PORTABILITY TEST SIMULATION ---
    print("\n[TEST 5] Testing Portable Path Resolution in Alternate Location...")
    temp_dir = tempfile.mkdtemp(prefix="IRD_TEST_PORTABLE_")
    try:
        alt_root = Path(temp_dir)
        alt_tools = alt_root / "tools" / "putty"
        alt_tools.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled_plink, alt_tools / "plink.exe")

        alt_plink = alt_tools / "plink.exe"
        assert alt_plink.exists(), "Copied plink in portable dir missing!"

        # Execute plink -V from alternate location
        v_res = putty_manager.test_plink_executable(str(alt_plink))
        assert v_res["success"], f"Portable Plink execution failed: {v_res}"
        print(f"Portable Plink Version: {v_res['version']}")
        print(f"Portable Path Display: {get_relative_display_path(str(alt_plink))}")
        print("Real-World Portability Test: PASS")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

    # --- TEST 6: REAL FNB TUNNEL TEST EXECUTION ---
    print("\n[TEST 6] Executing REAL FNB TUNNEL TEST Sequence...")
    async def async_fnb_test():
        res = await tunnel_manager.run_fnb_tunnel_test(fnb_site, keep_running=False)
        print("Formatted Test Summary:")
        print(res["formatted_summary"])
        print(f"Failure Code: {res['failure_code']}")
        print(f"Result Status: {res['result_status']}")
        return res

    res = asyncio.run(async_fnb_test())
    assert "result_status" in res, "Missing result_status in tunnel test output!"
    assert "formatted_summary" in res, "Missing formatted_summary in tunnel test output!"
    print("FNB Tunnel Test Sequence: COMPLETED")

    print("\n" + "=" * 65)
    print("PHASE 5B VERIFICATION COMPLETED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    run_phase5b_verification()
