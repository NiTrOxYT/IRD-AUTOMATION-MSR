import os
import sys
import asyncio

# Add workspace root to sys.path
sys.path.insert(0, os.path.abspath("."))

from app.database.db import get_site_by_id, init_db
from app.tunneling.tunnel_manager import tunnel_manager
from app.browser.browser_controller import browser_controller
from app.database.models import get_site_web_url

async def main_async():
    print("=================================================================")
    print("EXECUTING REAL LIVE PHASE 8 PLAYWRIGHT AUTOMATION RUN")
    print("=================================================================\n")

    init_db()

    site = get_site_by_id(22)
    assert site is not None, "Site 22 not found"

    print(f"Site Name: {site.name}")
    print(f"Site IP: {site.site_ip}")
    print(f"Site Port: {site.site_port}")
    print(f"Local Port: {site.local_port}")
    print(f"IDP Username: {site.idp_username}")

    web_url = get_site_web_url(site)
    print(f"Target ZMP URL: {web_url}\n")

    # Step 1: Establish & Verify Tunnel
    print("[STEP 1 & 2] Establishing Reverse SSH Tunnel & Endpoint Verification...")
    t_res = await tunnel_manager.run_fnb_tunnel_test(site, keep_running=True)
    print(f"Tunnel Result: {t_res['result_status']}")
    print("Tunnel Logs:")
    for l in t_res.get("logs", []):
        clean_l = l.encode("ascii", "ignore").decode("ascii")
        print(f"  {clean_l}")
    print()

    if t_res["checks"].get("fnb_service") != "PASS":
        print("CRITICAL ERROR: Tunnel validation failed. Aborting live Playwright run.")
        return

    # Step 3: Execute Real Phase 8 Playwright Workflow inside SAME async event loop
    print("[STEP 3] Launching Live Playwright Browser & Navigating to ZMP Portal...")
    try:
        p8_res = await browser_controller.run_fnb_login_and_sync_mymenu(site, web_url)
        print("\n=================================================================")
        print("LIVE PHASE 8 EXECUTION REPORT")
        print("=================================================================")
        clean_summary = p8_res.get("formatted_summary", "No formatted summary generated.").encode("ascii", "ignore").decode("ascii")
        print(clean_summary)
        print("\nExecution Logs:")
        for l in p8_res.get("logs", []):
            clean_l = l.encode("ascii", "ignore").decode("ascii")
            print(f"  {clean_l}")
        print("=================================================================")
    finally:
        print("\nCleaning up Plink test tunnel...")
        tunnel_manager.stop_tunnel(site)
        print("Plink test tunnel stopped cleanly.")

def main():
    asyncio.run(main_async())

if __name__ == "__main__":
    main()

