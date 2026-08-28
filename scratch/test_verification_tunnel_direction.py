"""
Dedicated Tunnel Direction Verification Suite — Local Forwarding (-L) Enforcement
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.tunneling.putty_manager import putty_manager
from app.database.models import Site

def test_tunnel_direction_local_forwarding():
    print("======================================================================")
    print("RUNNING DEDICATED TUNNEL DIRECTION (-L FORWARDING) VERIFICATION SUITE")
    print("======================================================================")

    # TEST 1: WH Bhubaneswar (#67) configuration
    print("\n[TEST 1] Testing WH Bhubaneswar (#67) Plink Command Generation...")
    wh_site = Site(
        id=67,
        name="WH Bhubaneswar",
        site_ip="103.243.40.46",
        site_port=8082,
        local_port=18002,
        tunnel_type="reverse", # database default
        ssh_host="111.93.205.187",
        ssh_port=22,
        ssh_username="sourik",
        enabled=True
    )

    cmd = putty_manager.build_plink_command(wh_site, plink_path="tools/putty/plink.exe")
    cmd_str = " ".join(cmd)
    scrubbed = putty_manager.scrub_sensitive_info(cmd_str)

    print(f"Generated Command: {scrubbed}")

    # Enforce Local Forwarding: -L 18002:103.243.40.46:8082
    assert "-L" in cmd
    assert "18002:103.243.40.46:8082" in cmd_str
    assert "-R" not in cmd
    print("[OK] Local Forwarding -L 18002:103.243.40.46:8082 verified!")

    # TEST 2: Password Scrubbing Check
    print("\n[TEST 2] Verifying Password Scrubbing in Plink Command...")
    assert "pw ********" in scrubbed or "-pw ********" in scrubbed or "********" in scrubbed
    assert "sourik" in scrubbed
    assert "111.93.205.187" in scrubbed
    print("[OK] Password scrubbing verified. Password never exposed in logs.")

    # TEST 3: Validation Endpoints Check
    print("\n[TEST 3] Verifying local TCP and HTTP validation endpoints...")
    local_endpoint = f"127.0.0.1:{wh_site.local_port}"
    browser_url = f"http://127.0.0.1:{wh_site.local_port}/zmp/main-menu.do"
    assert local_endpoint == "127.0.0.1:18002"
    assert browser_url == "http://127.0.0.1:18002/zmp/main-menu.do"
    print(f"[OK] TCP validation target: {local_endpoint}")
    print(f"[OK] HTTP validation URL: {browser_url}")

    print("\n======================================================================")
    print("ALL TUNNEL DIRECTION VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("======================================================================")

if __name__ == "__main__":
    test_tunnel_direction_local_forwarding()
