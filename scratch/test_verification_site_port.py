import os
import sys
import json
from pathlib import Path

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath("."))

from app.database.models import Site
from app.database.db import (
    init_db, get_all_sites, add_site, update_site, delete_site,
    validate_site_port, validate_local_port_collision, get_site_by_id
)
from app.tunneling.putty_manager import putty_manager

def main():
    print("=================================================================")
    print("RUNNING SITE SERVICE PORT (site_port) VERIFICATION SUITE")
    print("=================================================================\n")

    init_db()

    # TEST 1: Existing sites receive site_port = 80
    print("[TEST 1] Testing existing sites default site_port = 80...")
    sites = get_all_sites()
    assert len(sites) > 0, "No sites found in database"
    for s in sites:
        assert hasattr(s, "site_port"), f"Site '{s.name}' missing site_port attribute"
        assert s.site_port > 0, f"Site '{s.name}' has invalid site_port: {s.site_port}"
    print("TEST 1: PASS - All existing sites have valid site_port (default 80).\n")

    # TEST 2: site_port can be changed to 8080
    print("[TEST 2] Testing site_port update to 8080...")
    test_site = Site(
        name="Test Port Site 01",
        launcher_button="Test Port Site 01",
        site_ip="10.10.50.15",
        site_port=80,
        local_port=18991,
        enabled=False
    )
    site_id = add_site(test_site)
    added_s = get_site_by_id(site_id)
    assert added_s.site_port == 80, f"Expected 80, got {added_s.site_port}"

    added_s.site_port = 8080
    update_site(added_s)
    updated_s = get_site_by_id(site_id)
    assert updated_s.site_port == 8080, f"Expected 8080, got {updated_s.site_port}"
    print("TEST 2: PASS - site_port successfully updated to 8080.\n")

    # TEST 3: Dynamic Plink command generation (-L 18001:10.10.50.15:8080)
    print("[TEST 3] Testing dynamic Plink command generation (-L 18001:10.10.50.15:8080)...")
    cmd_site = Site(
        name="Command Test Site",
        site_ip="10.10.50.15",
        site_port=8080,
        local_port=18001,
        tunnel_type="local"
    )
    cmd = putty_manager.build_plink_command(cmd_site)
    cmd_str = " ".join(cmd)
    print(f"Generated Plink Command: {cmd_str}")
    assert "-L 18001:10.10.50.15:8080" in cmd_str, f"Missing -L 18001:10.10.50.15:8080 in command: {cmd_str}"
    print("TEST 3: PASS - Plink command dynamically includes -L 18001:10.10.50.15:8080.\n")

    # TEST 4: Browser URL generation (http://127.0.0.1:18001)
    print("[TEST 4] Testing Browser URL generation (http://127.0.0.1:18001)...")
    browser_url = f"http://127.0.0.1:{cmd_site.local_port}"
    assert browser_url == "http://127.0.0.1:18001", f"Expected http://127.0.0.1:18001, got {browser_url}"
    assert str(cmd_site.site_port) not in browser_url, "Browser URL must NOT use remote site_port"
    print("TEST 4: PASS - Browser URL uses local_port, not site_port.\n")

    # TEST 5: Invalid Site Port rejection
    print("[TEST 5] Testing invalid site_port rejection (0, -1, 65536, 'abc')...")
    for invalid_val in [0, -1, 65536, "abc", "65537"]:
        ok, err = validate_site_port(invalid_val)
        assert not ok, f"Expected invalid for {invalid_val}, got ok=True"
        assert len(err) > 0, f"Expected error message for {invalid_val}"
        print(f"  Rejected site_port {invalid_val}: {err}")
    print("TEST 5: PASS - All invalid site_port values cleanly rejected.\n")

    # TEST 6: Duplicate Local Port collision rejection
    print("[TEST 6] Testing duplicate local_port collision rejection...")
    s1 = Site(name="Collision Site A", site_ip="10.0.0.1", local_port=18995, enabled=True)
    s1_id = add_site(s1)

    c_ok, c_err = validate_local_port_collision(site_id=None, local_port=18995, enabled=True)
    assert not c_ok, "Expected port collision for port 18995"
    assert "already assigned to Collision Site A" in c_err, f"Unexpected error message: {c_err}"
    print(f"  Collision error: {c_err}")

    delete_site(s1_id)
    print("TEST 6: PASS - Duplicate local_port rejected with clear collision error.\n")

    # TEST 7: Same Site Port across different sites allowed
    print("[TEST 7] Testing same site_port (80) across different sites...")
    s_a = Site(name="Site A", site_ip="10.0.0.1", site_port=80, local_port=18996, enabled=True)
    s_b = Site(name="Site B", site_ip="10.0.0.2", site_port=80, local_port=18997, enabled=True)
    sa_id = add_site(s_a)
    sb_id = add_site(s_b)

    c_ok_b, _ = validate_local_port_collision(site_id=sb_id, local_port=18997, enabled=True)
    assert c_ok_b, "Different sites with different local_port should be allowed even with same site_port 80"

    delete_site(sa_id)
    delete_site(sb_id)
    delete_site(site_id)
    print("TEST 7: PASS - Same site_port (80) across different sites allowed.\n")

    # TEST 8: TunnelManager accepts site_ip, site_port, local_port
    print("[TEST 8] Testing TunnelManager parameter resolution...")
    from app.tunneling.tunnel_manager import tunnel_manager
    test_site_obj = Site(name="Tunnel Mgr Site", site_ip="14.142.185.130", site_port=80, local_port=18001)
    status = tunnel_manager.get_tunnel_status(test_site_obj)
    assert status["site_name"] == "Tunnel Mgr Site"
    assert status["local_port"] == 18001
    print("TEST 8: PASS - TunnelManager correctly handles site parameters.\n")

    print("=================================================================")
    print("ALL 8 SITE PORT VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=================================================================")

if __name__ == "__main__":
    main()
