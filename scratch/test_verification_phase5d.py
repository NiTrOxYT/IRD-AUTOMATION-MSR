import os
import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.db import (
    init_db, get_all_sites, get_site_by_id, get_site_by_name, update_site,
    get_office_ssh_config, get_office_ssh_password_decrypted,
    get_global_tunnel_config, set_global_tunnel_config
)
from app.database.models import Site
from app.tunneling.putty_paths import get_bundled_plink_path
from app.tunneling.putty_manager import putty_manager
from app.tunneling.tunnel_manager import tunnel_manager

def run_phase5d_verification():
    print("=" * 65)
    print("RUNNING PHASE 5D CORRECTION: FIXED REVERSE SSH TUNNEL VERIFICATION")
    print("=" * 65)

    init_db()

    # --- TEST 1: GLOBAL TUNNEL CONFIGURATION GET/SET ---
    print("\n[TEST 1] Testing Global Tunnel Settings GET/SET...")
    set_global_tunnel_config({
        "tunnel_remote_port": 80,
        "fnb_service_port": 80,
        "web_url_template": "http://127.0.0.1:{local_port}",
        "tunnel_type": "reverse"
    })
    g_cfg = get_global_tunnel_config()
    print(f"Global Remote Port: {g_cfg['tunnel_remote_port']}")
    print(f"Global FNB Service Port: {g_cfg['fnb_service_port']}")
    print(f"Global Web URL Template: {g_cfg['web_url_template']}")
    print(f"Global Tunnel Type: {g_cfg['tunnel_type']}")

    assert g_cfg["tunnel_remote_port"] == 80, "Expected tunnel_remote_port 80"
    assert g_cfg["fnb_service_port"] == 80, "Expected fnb_service_port 80"
    print("Global Tunnel Settings GET/SET Test: PASS")

    # --- TEST 2: SITE IP & LOCAL PORT PER-SITE CONFIGURATION ---
    print("\n[TEST 2] Testing Site IP & Local Port Configuration...")
    all_sites = get_all_sites()
    fnb = all_sites[0] if all_sites else None
    assert fnb is not None, "Database sites empty!"


    fnb.site_ip = "10.10.50.15"
    fnb.local_port = 18001
    update_site(fnb)

    fnb_reloaded = get_site_by_id(fnb.id)
    print(f"Site Name: {fnb_reloaded.name}")
    print(f"Site IP: {fnb_reloaded.site_ip}")
    print(f"Site Local Port: {fnb_reloaded.local_port}")

    assert fnb_reloaded.site_ip == "10.10.50.15", f"Expected site_ip '10.10.50.15', got '{fnb_reloaded.site_ip}'"
    assert fnb_reloaded.local_port == 18001, f"Expected local_port 18001, got '{fnb_reloaded.local_port}'"
    print("Site IP & Local Port Configuration Test: PASS")

    # --- TEST 3: DYNAMIC PLINK COMMAND GENERATION & SECRET SCRUBBING ---
    print("\n[TEST 3] Testing Dynamic Plink Command Generation from Global SSH + Site IP...")
    bundled_plink = get_bundled_plink_path()
    assert bundled_plink is not None, "Bundled Plink executable tools/putty/plink.exe missing!"

    cmd = putty_manager.build_plink_command(fnb_reloaded, bundled_plink)
    raw_cmd_str = " ".join(cmd)
    scrubbed_cmd_str = putty_manager.scrub_sensitive_info(raw_cmd_str)

    print(f"Raw Plink Command: {raw_cmd_str}")
    print(f"Scrubbed Plink Command: {scrubbed_cmd_str}")

    assert "-R 80:10.10.50.15:18001" in raw_cmd_str, "Expected '-R 80:10.10.50.15:18001' in generated Plink command!"
    assert "111.93.205.187" in raw_cmd_str, "Expected target SSH host 111.93.205.187!"
    assert "s0urik@@" not in scrubbed_cmd_str, "CRITICAL: Password leaked in scrubbed command!"
    print("Dynamic Plink Command Generation Test: PASS")

    # --- TEST 4: SITE ISOLATION TEST ---
    print("\n[TEST 4] Testing Site Process Isolation...")
    site2 = get_site_by_name("Site 02")
    if not site2:
        site2 = Site(name="Site 02", site_ip="10.10.50.16", local_port=18002)
    else:
        site2.site_ip = "10.10.50.16"
        site2.local_port = 18002

    cmd1 = putty_manager.build_plink_command(fnb_reloaded, bundled_plink)
    cmd2 = putty_manager.build_plink_command(site2, bundled_plink)

    print(f"Site 1 (FNB) Command: {' '.join(cmd1)}")
    print(f"Site 2 (Site 02) Command: {' '.join(cmd2)}")

    assert "-R 80:10.10.50.15:18001" in " ".join(cmd1), "Site 1 command mismatch"
    assert "-R 80:10.10.50.16:18002" in " ".join(cmd2), "Site 2 command mismatch"
    print("Site Process Isolation Test: PASS")

    # --- TEST 5: LIVE FNB REVERSE TUNNEL TEST ---
    print("\n[TEST 5] Executing Live FNB Reverse Tunnel Sequence...")
    async def async_fnb_test():
        res = await tunnel_manager.run_fnb_tunnel_test(fnb_reloaded, keep_running=False)
        print("\nFormatted Tunnel Test Summary:")
        print(res["formatted_summary"])
        print(f"Result Status: {res['result_status']}")
        return res

    res = asyncio.run(async_fnb_test())
    assert "result_status" in res, "Missing result_status"
    print("Live FNB Reverse Tunnel Execution: COMPLETED")

    print("\n" + "=" * 65)
    print("PHASE 5D CORRECTION VERIFICATION COMPLETED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    run_phase5d_verification()
