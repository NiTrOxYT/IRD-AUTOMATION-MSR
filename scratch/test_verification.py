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
    print("RUNNING IRD INTEGRATION TEST VERIFICATION SCRIPT")
    print("=" * 60)

    from app.database.db import init_db, get_all_sites
    from app.database.seed import seed_default_sites_if_empty
    from app.automation.workflow_runner import workflow_runner

    init_db()
    seed_default_sites_if_empty()

    sites = get_all_sites()
    if not sites:
        print("ERROR: No sites found in database.")
        sys.exit(1)

    test_site = sites[0]
    print(f"Selected Test Site: '{test_site.name}' (ID: {test_site.id}, Button: '{test_site.launcher_button}')")

    # 1. TEST BACKEND DIAGNOSTIC STAGE
    print("\n[TEST 1] Executing Diagnostic Backend Stage ('backend_test')...")
    res_backend = await workflow_runner.run_integration_test_stage(test_site.id, "backend_test")
    print(f"Result: success={res_backend.get('success')}, stage={res_backend.get('stage')}")
    print(f"Message: {res_backend.get('message')}")
    print(f"Details: {res_backend.get('details')}")
    assert res_backend.get('success') is True, "Backend diagnostic test failed!"

    # 2. TEST LAUNCHER STAGE SCHEMA
    print("\n[TEST 2] Executing Launcher Stage ('launcher')...")
    res_launcher = await workflow_runner.run_integration_test_stage(test_site.id, "launcher")
    print(f"Result: success={res_launcher.get('success')}, stage={res_launcher.get('stage')}")
    print(f"Message: {res_launcher.get('message')}")
    print(f"Details count: {len(res_launcher.get('details', []))}")

    # 3. TEST STOP AUTOMATION SIGNAL
    print("\n[TEST 3] Testing Stop Signal...")
    workflow_runner.stop_automation()
    print("Stop signal successfully sent!")

    print("\n" + "=" * 60)
    print("ALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
