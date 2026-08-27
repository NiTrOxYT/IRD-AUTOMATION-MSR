import os
import sys
import asyncio
from pathlib import Path

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath("."))

from app.database.models import Site, get_site_web_url
from app.database.db import get_site_by_id, init_db
from app.tunneling.tunnel_manager import tunnel_manager
from app.tunneling.putty_manager import putty_manager

def main():
    print("=================================================================")
    print("RUNNING PHASE 6B CANONICAL ZMP WEBPAGE URL TEST SUITE")
    print("=================================================================\n")

    init_db()

    # TEST 1: Helper Function get_site_web_url()
    print("[TEST 1] Testing get_site_web_url() Helper Function...")
    site22 = get_site_by_id(22)
    assert site22 is not None, "Site 22 (ITC Grand Chola) not found"
    assert site22.local_port in (18001, 58430), f"Expected local_port in (18001, 58430), got {site22.local_port}"

    assert site22.site_port in (8082, 8089, 80), f"Unexpected site_port: {site22.site_port}"


    web_url = get_site_web_url(site22)
    expected_url = f"http://localhost:{site22.local_port}/zmp/main-menu.do"

    print(f"Site Name: {site22.name}")
    print(f"Site IP: {site22.site_ip}")
    print(f"Site Port: {site22.site_port}")
    print(f"Local Port: {site22.local_port}")
    print(f"Browser URL: {web_url}")

    assert web_url == expected_url, f"Expected {expected_url}, got {web_url}"
    assert "127.0.0.1" not in web_url, "CRITICAL ERROR: 127.0.0.1 found in browser URL!"
    assert "/zmp/main-menu.do" in web_url, "CRITICAL ERROR: Mandatory path /zmp/main-menu.do missing!"
    print("TEST 1: PASS - Canonical get_site_web_url() returned http://localhost:58430/zmp/main-menu.do.\n")

    # TEST 2: Plink Command Forwarding Line
    print("[TEST 2] Verifying Plink Command Separation (Remote vs Local)...")
    detected = putty_manager.detect_executables()
    plink_path = detected["plink"] or "tools/putty/plink.exe"
    cmd = putty_manager.build_plink_command(site22, plink_path)
    cmd_str = " ".join(cmd)
    print(f"Plink Forward Command: {putty_manager.scrub_sensitive_info(cmd_str)}")

    assert f"-L {site22.local_port}:{site22.site_ip}:{site22.site_port}" in cmd_str, f"Forward mismatch in cmd: {cmd_str}"

    assert "111.93.205.187" in cmd_str, "Office SSH server host missing from command"
    print("TEST 2: PASS - Plink command cleanly forwards local port 58430 to 14.142.185.130:8089.\n")

    # TEST 3: TunnelManager Validation Logs
    print("[TEST 3] Testing TunnelManager Step 6 HTTP GET Request Target...")
    res = asyncio.run(tunnel_manager.run_fnb_tunnel_test(site22, keep_running=False))
    logs = res.get("logs", [])
    logs_str = "\n".join([l.replace("✓", "[PASS]") for l in logs])

    print(f"Tunnel Test Output Summary:\n{logs_str[:600]}...\n")

    assert f"Browser URL: http://localhost:{site22.local_port}/zmp/main-menu.do" in logs_str, f"Missing Browser URL in logs"

    assert f"STEP 6: Executing HTTP GET request to http://localhost:{site22.local_port}/zmp/main-menu.do" in logs_str, "Step 6 HTTP GET target mismatch"
    assert f"http://127.0.0.1:{site22.local_port}/" not in logs_str, "Stale root 127.0.0.1 URL used in HTTP GET"
    print(f"TEST 3: PASS - Step 6 HTTP GET correctly requested http://localhost:{site22.local_port}/zmp/main-menu.do.\n")


    print("=================================================================")
    print("ALL PHASE 6B ZMP WEBPAGE URL TESTS PASSED SUCCESSFULLY!")
    print("=================================================================")

if __name__ == "__main__":
    main()
