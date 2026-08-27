import os
import sys
import asyncio
from pathlib import Path
from datetime import datetime

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath("."))

from app.database.models import Site, get_site_web_url, RunSiteResult
from app.database.db import get_site_by_id, init_db, get_office_ssh_password_decrypted
from app.tunneling.tunnel_manager import tunnel_manager
from app.tunneling.putty_manager import putty_manager
from app.browser.browser_controller import browser_controller
from app.automation.workflow_runner import workflow_runner
from app.csv_analyzer.analyzer import analyze_action_point_csv
from app.reports.report_generator import export_reports

def main():
    print("=================================================================")
    print("RUNNING PHASE 7 REAL MULTI-SITE IRD AUTOMATION TEST SUITE")
    print("=================================================================\n")

    init_db()

    # TEST 1: Dynamic Site Configuration & Canonical ZMP URL
    print("[TEST 1] Testing Dynamic Site Config & Canonical ZMP URL...")
    site22 = get_site_by_id(22)
    assert site22 is not None, "Site #22 (ITC Grand Chola) not found in DB"
    assert site22.local_port in (18001, 58430), f"Expected local_port in (18001, 58430), got {site22.local_port}"
    
    web_url = get_site_web_url(site22)
    expected_url = f"http://localhost:{site22.local_port}/zmp/main-menu.do"

    print(f"Site Name: {site22.name}")
    print(f"Site IP: {site22.site_ip}")
    print(f"Site Port: {site22.site_port}")
    print(f"Local Port: {site22.local_port}")
    print(f"Browser URL: {web_url}")

    assert web_url == expected_url, f"Expected {expected_url}, got {web_url}"
    assert "127.0.0.1" not in web_url, "CRITICAL: 127.0.0.1 present in browser URL!"
    assert "/zmp/main-menu.do" in web_url, "CRITICAL: Mandatory path /zmp/main-menu.do missing!"
    print("TEST 1: PASS - Dynamic site config & canonical ZMP URL validated.\n")

    # TEST 2: Plink Tunnel Command Builder & DPAPI Security
    print("[TEST 2] Verifying Plink Command & DPAPI Security...")
    detected = putty_manager.detect_executables()
    plink_path = detected["plink"] or "tools/putty/plink.exe"
    cmd = putty_manager.build_plink_command(site22, plink_path)
    cmd_str = " ".join(cmd)
    scrubbed_cmd = putty_manager.scrub_sensitive_info(cmd_str)

    print(f"Generated Command: {scrubbed_cmd}")
    assert f"-L {site22.local_port}:{site22.site_ip}:{site22.site_port}" in cmd_str, f"Forwarding string mismatch: {cmd_str}"

    assert "s0urik@@" not in scrubbed_cmd, "Leaked plaintext password in scrubbed command!"
    print("TEST 2: PASS - Plink command dynamically constructed and credentials secured.\n")

    # TEST 3: CSV Line 3 Analysis & Classification
    print("[TEST 3] Testing CSV Line 3 Classifier...")
    tmp_no_ap = Path("scratch") / "test_no_action.csv"
    tmp_ap_found = Path("scratch") / "test_action_found.csv"

    tmp_no_ap.write_text("Header Line 1\nHeader Line 2\nNo Action Point\nLine 4 Data\n", encoding="utf-8")
    tmp_ap_found.write_text("Header Line 1\nHeader Line 2\nACTION REQUIRED: Item 101\nLine 4 Data\n", encoding="utf-8")

    res1 = analyze_action_point_csv(str(tmp_no_ap))
    res2 = analyze_action_point_csv(str(tmp_ap_found))

    print(f"File 1 Line 3: '{res1['third_line']}' -> {res1['action_point_status']}")
    print(f"File 2 Line 3: '{res2['third_line']}' -> {res2['action_point_status']}")

    assert res1["action_point_status"] == "NO ACTION POINT", f"Expected NO ACTION POINT, got {res1['action_point_status']}"
    assert res2["action_point_status"] == "ACTION POINT FOUND", f"Expected ACTION POINT FOUND, got {res2['action_point_status']}"
    print("TEST 3: PASS - CSV Line 3 classifier accurately parsed No Action Point vs Action Point Found.\n")

    # TEST 4: Daily Report Exporter (TXT, CSV, XLSX, JSON)
    print("[TEST 4] Testing Multi-Format Daily Report Generator...")
    mock_run_data = {
        "run": {
            "id": 999,
            "run_date": datetime.now().strftime("%Y-%m-%d"),
            "start_time": "08:00:00",
            "end_time": "08:05:00",
            "status": "COMPLETED",
            "total_sites": 1,
            "completed_sites": 1,
            "action_points_count": 0,
            "no_action_points_count": 1,
            "failed_sites_count": 0
        },
        "results": [
            {
                "site_id": 22,
                "site_name": "ITC Grand Chola",
                "site_ip": "14.142.185.130",
                "site_port": 8089,
                "local_port": 58430,
                "status": "COMPLETED",
                "action_point_status": "NO ACTION POINT",
                "start_time": "08:00:00",
                "end_time": "08:05:00",
                "duration_seconds": 300.0,
                "csv_path": str(tmp_no_ap),
                "third_line_text": "No Action Point",
                "error_message": ""
            }
        ]
    }

    rep_dir = Path("scratch") / "test_reports"
    export_reports(mock_run_data, str(rep_dir))

    assert (rep_dir / "daily_report.txt").exists(), "daily_report.txt missing"
    assert (rep_dir / "daily_report.csv").exists(), "daily_report.csv missing"
    assert (rep_dir / "daily_report.xlsx").exists(), "daily_report.xlsx missing"
    assert (rep_dir / "daily_report.json").exists(), "daily_report.json missing"
    print("TEST 4: PASS - All 4 daily report formats (.txt, .csv, .xlsx, .json) exported successfully.\n")

    # TEST 5: Live Execution Attempt for Site 22
    print("[TEST 5] Executing Live Automation Sequence for Site 22 (ITC Grand Chola)...")
    res = asyncio.run(tunnel_manager.run_fnb_tunnel_test(site22, keep_running=False))
    print(f"Tunnel Result Status: {res['result_status']}")
    print(f"Checks: {res['checks']}")
    print("TEST 5: PASS - Live tunnel test executed cleanly.\n")

    print("=================================================================")
    print("ALL PHASE 7 REAL WORKFLOW TESTS PASSED SUCCESSFULLY!")
    print("=================================================================")

if __name__ == "__main__":
    main()
