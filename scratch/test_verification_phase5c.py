import os
import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.db import (
    init_db, get_all_sites, get_site_by_id, get_site_by_name,
    seed_office_ssh_credentials_if_empty, get_office_ssh_config,
    get_office_ssh_password_decrypted, set_office_ssh_config
)
from app.tunneling.putty_paths import get_bundled_plink_path
from app.tunneling.putty_manager import putty_manager
from app.tunneling.tunnel_manager import tunnel_manager

def run_phase5c_verification():
    print("=" * 65)
    print("RUNNING PHASE 5C: OFFICE SERVER SSH CONFIGURATION VERIFICATION")
    print("=" * 65)

    init_db()

    # --- TEST 1: DPAPI CREDENTIAL SEEDING & PRESERVATION ---
    print("\n[TEST 1] Testing DPAPI Credential Seeding & Preservation...")
    seed_office_ssh_credentials_if_empty()
    cfg = get_office_ssh_config()

    print(f"SSH Host: {cfg['ssh_host']}")
    print(f"SSH Port: {cfg['ssh_port']}")
    print(f"SSH Username: {cfg['ssh_username']}")
    print(f"Auth Type: {cfg['auth_type']}")
    print(f"Password Configured: {cfg['password_configured']}")

    # Verify password plaintext is NEVER in get_office_ssh_config()
    assert "ssh_password" not in cfg, "CRITICAL SECURITY: ssh_password leaked in config dict!"
    assert cfg["password_configured"] is True, "Expected password_configured to be True!"

    # Verify DPAPI decrypted password in memory only
    dec_pass = get_office_ssh_password_decrypted()
    assert dec_pass == "s0urik@@", f"Expected decrypted password 's0urik@@', got '{dec_pass}'"
    print("DPAPI Credential Seeding Test: PASS")

    # --- TEST 2: PLINK SSH TEST COMMAND CONSTRUCTION & SCRUBBING ---
    print("\n[TEST 2] Testing SSH Test Command Construction & Secret Scrubbing...")
    bundled_plink = get_bundled_plink_path()
    assert bundled_plink is not None, "Bundled Plink executable tools/putty/plink.exe missing!"

    cfg_exec = dict(cfg)
    cfg_exec["ssh_password"] = dec_pass

    cmd = putty_manager.build_ssh_test_command(cfg_exec, bundled_plink)
    raw_cmd_str = " ".join(cmd)
    scrubbed_cmd_str = putty_manager.scrub_sensitive_info(raw_cmd_str)

    print(f"Raw command contains password: {'s0urik@@' in raw_cmd_str}")
    print(f"Scrubbed command: {scrubbed_cmd_str}")

    assert "s0urik@@" not in scrubbed_cmd_str, "CRITICAL: Password leaked in scrubbed command!"
    assert "-pw ********" in scrubbed_cmd_str, "Expected -pw ******** in scrubbed command!"
    print("SSH Command Construction & Secret Scrubbing Test: PASS")

    # --- TEST 3: FNB SITE CONFIGURATION SYNC ---
    print("\n[TEST 3] Testing FNB Site Configuration Sync...")
    all_sites = get_all_sites()
    fnb_site = all_sites[0] if all_sites else None
    assert fnb_site is not None, "FNB Site record not found!"


    ssh_cfg = get_office_ssh_config()
    print(f"Global Office SSH Host: {ssh_cfg['ssh_host']}")
    print(f"Global Office SSH User: {ssh_cfg['ssh_username']}")

    assert ssh_cfg["ssh_host"] == "111.93.205.187", "Office SSH Host mismatch!"
    assert ssh_cfg["ssh_username"] == "sourik", "Office SSH Username mismatch!"
    assert get_office_ssh_password_decrypted() == "s0urik@@", "Office SSH Password DPAPI decryption mismatch!"
    print("FNB Site Configuration Sync Test: PASS")


    # --- TEST 4: REAL OFFICE SSH SERVER CONNECTION TEST ---
    print("\n[TEST 4] Executing Live Office SSH Server Connection Test (111.93.205.187:22)...")
    async def async_ssh_test():
        res = await tunnel_manager.test_office_ssh_connection()
        print("\nFormatted SSH Test Summary:")
        print(res["formatted_summary"])
        print(f"Result Message: {res['result_message']}")
        return res

    ssh_res = asyncio.run(async_ssh_test())
    assert "result_message" in ssh_res, "Missing result_message in SSH test result!"
    assert "formatted_summary" in ssh_res, "Missing formatted_summary in SSH test result!"
    print("Office SSH Connection Test Execution: COMPLETED")

    # --- TEST 5: REAL FNB TUNNEL TEST EXECUTION ---
    print("\n[TEST 5] Executing REAL FNB TUNNEL TEST Sequence...")
    async def async_fnb_test():
        res = await tunnel_manager.run_fnb_tunnel_test(fnb_site, keep_running=False)
        print("\nFormatted FNB Tunnel Test Summary:")
        print(res["formatted_summary"])
        print(f"Failure Code: {res['failure_code']}")
        print(f"Result Status: {res['result_status']}")
        return res

    fnb_res = asyncio.run(async_fnb_test())
    assert "result_status" in fnb_res, "Missing result_status in FNB tunnel test result!"
    print("REAL FNB Tunnel Test Execution: COMPLETED")

    print("\n" + "=" * 65)
    print("PHASE 5C VERIFICATION COMPLETED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    run_phase5c_verification()
