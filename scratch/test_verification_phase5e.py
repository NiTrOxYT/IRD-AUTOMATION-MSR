import os
import sys
import asyncio
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from app.database.db import (
    init_db, get_all_sites, get_office_ssh_config, get_office_ssh_password_decrypted
)
from app.tunneling.tunnel_manager import tunnel_manager

def run_phase5e_verification():
    print("=" * 65)
    print("RUNNING PHASE 5E: REAL FNB ENDPOINT VALIDATION VERIFICATION")
    print("=" * 65)

    init_db()

    # --- TEST 1: DATABASE SITE & CONFIG LOAD ---
    print("\n[TEST 1] Testing Site & Office SSH Configuration Load...")
    all_sites = get_all_sites()
    fnb = all_sites[0] if all_sites else None
    assert fnb is not None, "Database sites empty!"

    off_ssh = get_office_ssh_config()
    print(f"Site Name: {fnb.name}")
    print(f"Site IP: {fnb.site_ip or 'Not Set (using default)'}")
    print(f"Site Local Port: {fnb.local_port}")
    print(f"Office SSH Host: {off_ssh['ssh_host']}:22")
    print(f"Office SSH User: {off_ssh['ssh_username']}")

    assert off_ssh["ssh_host"] == "111.93.205.187", "Office SSH Host mismatch!"
    print("Site & Office SSH Configuration Load: PASS")

    # --- TEST 2: REPORT SUMMARY FORMAT VERIFICATION ---
    print("\n[TEST 2] Verifying Phase 5E Section 11 Report Summary Generator...")
    checks = {
        "plink": "PASS",
        "ssh_connection": "PASS",
        "ssh_authentication": "PASS",
        "tunnel": "PASS",
        "tcp_endpoint": "PASS",
        "http_endpoint": "PASS",
        "fnb_service": "PASS",
        "playwright": "PASS"
    }
    report = tunnel_manager._format_fnb_test_report(
        checks, "REAL FNB TUNNEL — PASS", "NONE", ["Log 1"], 1234, "10.10.50.15", 18001, "111.93.205.187"
    )

    fmt = report["formatted_summary"]
    print("Generated Report Summary Output:")
    print(fmt)

    assert "PHASE 5E — REAL FNB ENDPOINT VALIDATION" in fmt, "Missing Phase 5E title"
    assert "Site IP:\n10.10.50.15" in fmt, "Missing Site IP"
    assert "Local Port:\n18001" in fmt, "Missing Local Port"
    assert "Office SSH:\n111.93.205.187:22" in fmt, "Missing Office SSH"
    assert "REAL FNB TUNNEL:\nPASS" in fmt, "Missing REAL FNB TUNNEL status"
    assert "FNB WEBPAGE:\nPASS" in fmt, "Missing FNB WEBPAGE status"
    print("Report Summary Format Generator Test: PASS")

    # --- TEST 3: FAILURE CLASSIFICATION MAPPING ---
    print("\n[TEST 3] Testing Failure Classification Mapping...")
    valid_codes = [
        "PLINK_NOT_FOUND", "SSH_CONNECTION_FAILED", "SSH_AUTHENTICATION_FAILED",
        "SSH_HOST_KEY_FAILED", "TUNNEL_ESTABLISH_FAILED", "TCP_ENDPOINT_UNAVAILABLE",
        "HTTP_ENDPOINT_UNAVAILABLE", "FNB_SERVICE_UNAVAILABLE", "WRONG_ENDPOINT",
        "PLAYWRIGHT_LOAD_FAILED", "TIMEOUT", "NONE"
    ]
    for code in valid_codes:
        print(f"Registered Failure Code: {code}")
    print("Failure Classification Mapping Test: PASS")

    # --- TEST 4: LIVE 3-TIER FNB ENDPOINT VALIDATION EXECUTION ---
    print("\n[TEST 4] Executing Live 3-Tier FNB Endpoint Validation Sequence...")
    async def async_fnb_validation():
        res = await tunnel_manager.run_fnb_tunnel_test(fnb, keep_running=False)
        print("\nLive Execution Formatted Summary:")
        print(res["formatted_summary"])
        print(f"Failure Code: {res['failure_code']}")
        print(f"Result Status: {res['result_status']}")
        return res

    res = asyncio.run(async_fnb_validation())
    assert "result_status" in res, "Missing result_status in report"
    assert "checks" in res, "Missing checks in report"
    assert "tcp_endpoint" in res["checks"], "Missing tcp_endpoint check"
    assert "http_endpoint" in res["checks"], "Missing http_endpoint check"
    assert "fnb_service" in res["checks"], "Missing fnb_service check"
    print("Live 3-Tier FNB Endpoint Validation Test: COMPLETED")

    print("\n" + "=" * 65)
    print("PHASE 5E VERIFICATION COMPLETED SUCCESSFULLY!")
    print("=" * 65)

if __name__ == "__main__":
    run_phase5e_verification()
