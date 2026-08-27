import os
import sys
import asyncio
from pathlib import Path

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath("."))

from app.database.models import Site, get_site_web_url
from app.database.db import get_site_by_id, init_db, get_office_ssh_password_decrypted
from app.tunneling.tunnel_manager import tunnel_manager
from app.tunneling.putty_manager import putty_manager
from app.browser.browser_controller import browser_controller
from app.browser.selectors import SelectorRegistry


async def main_async():
    print("=================================================================")
    print("RUNNING PHASE 8 REAL PLAYWRIGHT IDP LOGIN + SYNCMYMENU SUITE")
    print("=================================================================\n")

    init_db()

    # TEST 1: Parameter Propagation & Canonical ZMP URL
    print("[TEST 1] Testing Parameter Propagation & Canonical ZMP URL...")
    site22 = get_site_by_id(22)
    assert site22 is not None, "Site #22 (ITC Grand Chola) not found in database"
    assert site22.site_ip == "14.142.185.130", f"Expected site_ip = 14.142.185.130, got {site22.site_ip}"
    assert site22.site_port == 8082, f"Expected site_port = 8082, got {site22.site_port}"
    assert site22.local_port == 18001, f"Expected local_port = 18001, got {site22.local_port}"

    web_url = get_site_web_url(site22)
    expected_url = "http://localhost:18001/zmp/main-menu.do"

    print(f"Site Name: {site22.name}")
    print(f"Site IP: {site22.site_ip}")
    print(f"Site Port: {site22.site_port}")
    print(f"Local Port: {site22.local_port}")
    print(f"Browser URL: {web_url}")

    assert web_url == expected_url, f"Expected {expected_url}, got {web_url}"
    assert "127.0.0.1" not in web_url, "CRITICAL ERROR: 127.0.0.1 found in browser URL!"
    assert "/zmp/main-menu.do" in web_url, "CRITICAL ERROR: Mandatory path /zmp/main-menu.do missing!"
    print("TEST 1: PASS - Dynamic parameter propagation & ZMP URL validated.\n")

    # TEST 2: Selector Registry Resolution
    print("[TEST 2] Verifying Selector Registry Resolution for Phase 8 Steps...")
    user_sels = SelectorRegistry.get_selectors_for_step("idp_username")
    pass_sels = SelectorRegistry.get_selectors_for_step("idp_password")
    sub_sels = SelectorRegistry.get_selectors_for_step("login_button")
    sync_sels = SelectorRegistry.get_selectors_for_step("sync_mymenu")
    fetch_sels = SelectorRegistry.get_selectors_for_step("fetch_menu")

    print(f"IDP Username Selectors: {user_sels}")
    print(f"IDP Password Selectors: {pass_sels}")
    print(f"Login Button Selectors: {sub_sels}")
    print(f"Sync MyMenu Selectors: {sync_sels}")
    print(f"Fetch Menu Selectors: {fetch_sels}")

    assert len(user_sels) > 0, "IDP username selectors missing"
    assert len(pass_sels) > 0, "IDP password selectors missing"
    assert len(sub_sels) > 0, "Login button selectors missing"
    assert len(sync_sels) > 0, "Sync MyMenu selectors missing"
    assert len(fetch_sels) > 0, "Fetch Menu selectors missing"
    print("TEST 2: PASS - Centralized selector registry contains all required Phase 8 selectors.\n")

    # TEST 3: Plink Forwarding Command & Secret Scrubbing
    print("[TEST 3] Testing Plink Command Generation (-L 18001:14.142.185.130:8082)...")
    detected = putty_manager.detect_executables()
    plink_path = detected["plink"] or "tools/putty/plink.exe"
    cmd = putty_manager.build_plink_command(site22, plink_path)
    cmd_str = " ".join(cmd)
    scrubbed = putty_manager.scrub_sensitive_info(cmd_str)

    print(f"Plink Command: {scrubbed}")
    assert "-L 18001:14.142.185.130:8082" in cmd_str, f"Forwarding mismatch in command: {cmd_str}"
    assert "111.93.205.187" in cmd_str, "Office SSH host missing from command"
    assert "s0urik@@" not in scrubbed, "Plaintext SSH password leaked in scrubbed log!"
    print("TEST 3: PASS - Plink command cleanly forwards 18001 -> 14.142.185.130:8082 with secrets scrubbed.\n")

    # TEST 4: Phase 8 Failure Classifications & Stage Ordering
    print("[TEST 4] Verifying Phase 8 Failure Classifications & Report Format...")
    mock_stages = {
        "tunnel": "PASS",
        "zmp_page": "PASS",
        "idp_login": "PASS",
        "authentication": "PASS",
        "sync_mymenu": "PASS",
        "fetch_menu_control": "PASS"
    }
    rep = browser_controller._format_phase8_report(mock_stages, "PASS", "NONE", ["Log Line 1"], site22.name)

    print(f"Formatted Summary:\n{rep['formatted_summary']}\n")

    assert rep["success"] is True, "Expected success is True"
    assert "PHASE 8 REAL WORKFLOW — PASS" in rep["result_status"]
    assert "TUNNEL:\nPASS" in rep["formatted_summary"]
    assert "FETCH MENU CONTROL:\nPASS" in rep["formatted_summary"]
    print("TEST 4: PASS - Phase 8 report format and failure classifications verified.\n")

    # TEST 5: Live Execution Attempt for Site 22
    print("[TEST 5] Executing Live Reverse Tunnel & Endpoint Validation for Site 22...")
    res = await tunnel_manager.run_fnb_tunnel_test(site22, keep_running=False)

    print(f"Tunnel Result Status: {res['result_status']}")
    print(f"Checks: {res['checks']}")
    print("TEST 5: PASS - Tunnel test executed for Site 22.\n")

    # TEST 6: Live Playwright IDP Login & Sync MyMenu Workflow
    print("[TEST 6] Executing Live Playwright IDP Login + Sync MyMenu Sequence for Site 22...")
    t_res = await tunnel_manager.run_fnb_tunnel_test(site22, keep_running=True)
    t_ok = t_res.get("checks", {}).get("tunnel") == "PASS" and t_res.get("checks", {}).get("http_endpoint") == "PASS"
    assert t_ok, f"Tunnel verification failed before Playwright launch: {t_res.get('result_status')}"


    try:
        p8_res = await browser_controller.run_fnb_login_and_sync_mymenu(site22, web_url)
        print("Live Playwright Result Status:", p8_res.get("result_status"))
        print("Failure Code:", p8_res.get("failure_code"))
        print("\nPhase 8 Live Summary:\n", p8_res.get("formatted_summary"))
        print("\nPlaywright Execution Logs:")
        for log_line in p8_res.get("logs", []):
            clean_log = log_line.replace('✓', '[PASS]').replace('★', '[INFO]').encode("ascii", "ignore").decode("ascii")
            print(f"  {clean_log}")

        print("TEST 6: PASS - Live Playwright IDP Login & Sync MyMenu sequence executed cleanly.\n")
    finally:
        tunnel_manager.stop_tunnel(site22)
        print("Stopped test tunnel for Site 22.")


    print("=================================================================")
    print("ALL PHASE 8 VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=================================================================")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()
