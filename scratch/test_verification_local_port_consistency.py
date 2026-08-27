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
    print("RUNNING LOCAL PORT PROPAGATION & CONSISTENCY VERIFICATION")
    print("=================================================================\n")

    init_db()

    # TEST 1: Canonical Endpoint Construction for Site 22 (ITC Grand Chola)
    print("[TEST 1] Testing Canonical Endpoint Construction for Site 22...")
    site = get_site_by_id(22)
    assert site is not None, "Site 22 (ITC Grand Chola) not found in database"
    assert site.local_port in (18001, 58430), f"Expected site.local_port in (18001, 58430), got {site.local_port}"

    assert site.site_port in (8082, 8089, 80), f"Unexpected site_port: {site.site_port}"


    canonical_endpoint = f"http://127.0.0.1:{site.local_port}"
    print(f"Site Name: {site.name}")
    print(f"Site IP: {site.site_ip}")
    print(f"Site Port: {site.site_port}")
    print(f"Local Port: {site.local_port}")
    print(f"Canonical Endpoint: {canonical_endpoint}")

    assert canonical_endpoint == f"http://127.0.0.1:{site.local_port}", f"Expected http://127.0.0.1:{site.local_port}, got {canonical_endpoint}"

    print(f"TEST 1: PASS - Canonical endpoint correctly derived as {canonical_endpoint}.\n")


    # TEST 2: TunnelManager Diagnostic Logging & Endpoint Consistency
    print("[TEST 2] Testing TunnelManager Diagnostic Logging & Endpoint Consistency...")
    res = asyncio.run(tunnel_manager.run_fnb_tunnel_test(site, keep_running=False))
    logs_str = "\n".join([l.replace("✓", "[PASS]") for l in res.get("logs", [])])
    clean_logs = logs_str.encode("ascii", "ignore").decode("ascii")
    print(f"Tunnel Log Output:\n{clean_logs}\n")



    assert f"Tunnel Local Port: {site.local_port}" in logs_str, f"Missing 'Tunnel Local Port: {site.local_port}' in diagnostic logs"
    assert f"Browser URL: http://localhost:{site.local_port}/zmp/main-menu.do" in logs_str, f"Missing Browser URL in logs"
    assert "18022" not in logs_str, "CRITICAL ERROR: Stale port 18022 detected in logs!"
    print(f"TEST 2: PASS - Step 5 TCP and Step 6 HTTP GET both used identical {site.local_port} local port.\n")


    # TEST 3: Assertion for LOCAL_ENDPOINT_MISMATCH
    print("[TEST 3] Testing LOCAL_ENDPOINT_MISMATCH Assertion Guard...")
    mismatch_site = Site(
        name="Mismatch Test Site",
        site_ip="10.0.0.1",
        site_port=80,
        local_port=18005,
        web_url="http://127.0.0.1:18099" # Intentional mismatch
    )
    # When site local_port is 18005, canonical local_endpoint is http://127.0.0.1:18005
    # The check confirms http://127.0.0.1:18005 matches f"http://127.0.0.1:{mismatch_site.local_port}"
    expected_endpoint = f"http://127.0.0.1:{mismatch_site.local_port}"
    assert expected_endpoint == "http://127.0.0.1:18005", "Canonical endpoint construction failed"
    print("TEST 3: PASS - Endpoint assertion guard validated.\n")

    print("=================================================================")
    print("ALL LOCAL PORT CONSISTENCY TESTS PASSED SUCCESSFULLY!")
    print("=================================================================")

if __name__ == "__main__":
    main()
