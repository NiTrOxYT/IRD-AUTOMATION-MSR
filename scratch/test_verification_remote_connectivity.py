import os
import sys
import asyncio
from pathlib import Path

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath("."))

from app.database.models import Site
from app.database.db import get_site_by_id, init_db
from app.tunneling.tunnel_manager import tunnel_manager

def main():
    print("=================================================================")
    print("RUNNING OFFICE -> SITE REMOTE CONNECTIVITY TEST SUITE")
    print("=================================================================\n")

    init_db()

    site = get_site_by_id(22)
    assert site is not None, "Site 22 (ITC Grand Chola) not found in database"

    print(f"Target Site: {site.name}")
    print(f"Target Site IP: {site.site_ip}")
    print(f"Configured Site Port: {site.site_port}")
    print(f"Local Port: {site.local_port}\n")

    # TEST 1: Execute Remote Connectivity Test from Office Server 111.93.205.187
    print("[TEST 1] Executing Remote Connectivity Test from Office Server...")
    res = asyncio.run(tunnel_manager.test_remote_site_connectivity(site))

    print(f"Office SSH Status: {res.get('ssh')}")
    print(f"Remote TCP Status: {res.get('remote_tcp')}")
    print(f"Remote HTTP Status: {res.get('remote_http')}")
    print(f"Failure Code: {res.get('failure_code')}")
    print(f"Port Tests: {res.get('port_tests')}\n")

    assert res["ssh"] == "PASS", f"Expected SSH PASS, got {res['ssh']}"
    assert "8089" in res["port_tests"], "Port 8089 missing from port_tests"
    assert "8080" in res["port_tests"], "Port 8080 missing from port_tests"
    assert res["port_tests"]["8080"] == "PASS", f"Expected Port 8080 PASS, got {res['port_tests']['8080']}"
    assert "FAIL" in res["port_tests"]["8089"], f"Expected Port 8089 FAIL, got {res['port_tests']['8089']}"
    print("TEST 1: PASS - Remote TCP scanner correctly identified reachable and closed ports.\n")

    # TEST 2: Secret Scrubbing Verification
    print("[TEST 2] Verifying Secret Scrubbing in Logs...")
    logs_str = "\n".join(res.get("logs", []))
    assert "s0urik@@" not in logs_str, "CRITICAL SECURITY ERROR: Plaintext SSH password leaked in logs!"
    assert "********" in logs_str or "password" not in logs_str.lower(), "Missing masked password token"
    print("TEST 2: PASS - Plaintext passwords cleanly scrubbed from all diagnostic logs.\n")

    print("=================================================================")
    print("ALL REMOTE CONNECTIVITY DIAGNOSTIC TESTS PASSED SUCCESSFULLY!")
    print("=================================================================")

if __name__ == "__main__":
    main()
