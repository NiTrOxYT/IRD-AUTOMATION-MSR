import os
import sys
import asyncio
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

async def main():
    print("=" * 60)
    print("RUNNING PHASE 4: PUTTY REVERSE TUNNEL VERIFICATION SCRIPT")
    print("=" * 60)

    from app.database.models import Site
    from app.database.db import init_db, get_all_sites, add_site, get_site_by_id
    from app.tunneling.port_manager import port_manager
    from app.tunneling.putty_manager import putty_manager
    from app.tunneling.tunnel_manager import tunnel_manager

    # 1. DATABASE MIGRATION & MODEL VERIFICATION
    print("\n[TEST 1] Testing Database Schema Migration & Tunnel Fields...")
    from app.database.seed import seed_default_sites_if_empty
    init_db()
    seed_default_sites_if_empty()
    sites = get_all_sites()
    print(f"Loaded {len(sites)} sites from database.")
    assert len(sites) > 0, "No sites loaded from database!"

    test_site = sites[0]
    print(f"Site 1 Name: '{test_site.name}', Local Port: {test_site.local_port}, Auth Type: '{test_site.auth_type}'")
    assert hasattr(test_site, 'local_port'), "Site model missing local_port!"
    assert hasattr(test_site, 'ssh_host'), "Site model missing ssh_host!"

    # 2. PORT MANAGER VERIFICATION
    print("\n[TEST 2] Testing PortManager Availability & Collision Detection...")
    is_18001_free = port_manager.verify_port_available(18001)
    print(f"Local port 18001 available: {is_18001_free}")

    has_collisions, conflicts = port_manager.check_site_port_collisions(sites)
    print(f"Port collisions detected: {has_collisions}")
    if conflicts:
        print(f"Collision details: {conflicts}")

    # 3. PUTTY MANAGER & PLINK COMMAND BUILDING
    print("\n[TEST 3] Testing PuTTY/Plink Detection & Command Construction...")
    detected = putty_manager.detect_executables()
    print(f"Detected executables: {detected}")

    mock_site = Site(
        id=99,
        name="TestSite",
        local_port=18005,
        remote_host="127.0.0.1",
        remote_port=80,
        ssh_host="gateway.test.internal",
        ssh_port=2222,
        ssh_username="tunnel_usr",
        ssh_password="SecretSSHPassword123!",
        auth_type="password"
    )

    cmd = putty_manager.build_plink_command(mock_site)
    cmd_str = " ".join(cmd)
    scrubbed_str = putty_manager.scrub_sensitive_info(cmd_str)
    print(f"Raw Built Command: {cmd_str}")
    print(f"Scrubbed Log Command: {scrubbed_str}")

    assert "SecretSSHPassword123!" not in scrubbed_str, "Password leak in scrubbed command output!"
    assert "********" in scrubbed_str, "Password scrubbing failed!"

    # 4. TUNNEL MANAGER STATUS DICTIONARY
    print("\n[TEST 4] Testing TunnelManager Status Output...")
    status = tunnel_manager.get_tunnel_status(test_site)
    print(f"Tunnel Status for {test_site.name}: {status}")
    assert status["status"] in ("STOPPED", "DISCONNECTED", "CONNECTED"), "Invalid tunnel status!"

    print("\n" + "=" * 60)
    print("PHASE 4 VERIFICATION COMPLETED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
