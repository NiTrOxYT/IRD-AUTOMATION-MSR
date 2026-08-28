"""
Dedicated Verification Suite — Run History Persistence, API, and Formatting
"""
import os
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.database.db import (
    init_db, create_run, update_run, save_run_site_result,
    get_runs_history, get_run_details
)
from app.database.models import Run, RunSiteResult

def test_run_history_today():
    print("======================================================================")
    print("RUNNING TODAY'S RUN HISTORY PERSISTENCE & API VERIFICATION SUITE")
    print("======================================================================")

    init_db()
    today_str = datetime.now().strftime("%Y-%m-%d")

    # TEST 1: Create and persist a completed batch run with 2 sites (1 SUCCESS, 1 FAILED)
    print("\n[TEST 1] Creating and persisting a completed batch run with 2 sites...")
    run_1 = Run(
        run_date=today_str,
        start_time=datetime.now().strftime("%I:%M %p"),
        status="IN_PROGRESS",
        total_sites=2,
        completed_sites=0,
        action_points_count=0,
        no_action_points_count=0,
        failed_sites_count=0
    )
    run_id_1 = create_run(run_1)
    run_1.id = run_id_1

    # Site 1: Successful WH Bhubaneswar with ACTION POINT FOUND
    res_1 = RunSiteResult(
        run_id=run_id_1,
        site_id=67,
        site_name="WH Bhubaneswar",
        status="COMPLETED",
        action_point_status="ACTION POINT FOUND",
        fetch_menu_status="SUCCESS",
        process_latest_menu_status="SUCCESS",
        download_status="SUCCESS",
        failure_code="NONE"
    )
    save_run_site_result(res_1)

    # Site 2: Failed ITC Kohenur with LAST_RECEIVED_DATE_NOT_CURRENT
    res_2 = RunSiteResult(
        run_id=run_id_1,
        site_id=68,
        site_name="ITC Kohenur",
        status="FAILED",
        action_point_status="FAILED",
        fetch_menu_status="FAILED",
        process_latest_menu_status="BLOCKED",
        download_status="BLOCKED",
        failure_code="LAST_RECEIVED_DATE_NOT_CURRENT"
    )
    save_run_site_result(res_2)

    # Update run_1 summary counters
    run_1.end_time = datetime.now().strftime("%I:%M %p")
    run_1.status = "COMPLETED"
    run_1.completed_sites = 1
    run_1.failed_sites_count = 1
    run_1.action_points_count = 1
    run_1.no_action_points_count = 0
    update_run(run_1)

    print("[OK] Test 1: Batch run and 2 site results persisted into DB.")

    # TEST 2: Verify get_runs_history returns today's run
    print("\n[TEST 2] Verifying get_runs_history API returns today's run...")
    history = get_runs_history(limit=50)
    assert len(history) > 0, "History list is empty!"

    today_runs = [r for r in history if r["id"] == run_id_1]
    assert len(today_runs) == 1, "Persisted run not found in history API!"
    r1_data = today_runs[0]

    assert r1_data["run_date"] == today_str
    assert r1_data["total_sites"] == 2
    assert r1_data["completed_sites"] == 1
    assert r1_data["failed_sites_count"] == 1
    assert r1_data["action_points_count"] == 1
    assert r1_data["no_action_points_count"] == 0
    assert r1_data["status"] == "COMPLETED"
    assert "results" in r1_data
    assert len(r1_data["results"]) == 2
    print("[OK] Test 2: Today's run returned by API with correct summary counters.")

    # TEST 3: Verify get_run_details API returns successful and failed site details
    print("\n[TEST 3] Verifying get_run_details returns site stage-level details...")
    details = get_run_details(run_id_1)
    assert details is not None
    results = details["results"]

    wh_res = next(s for s in results if s["site_name"] == "WH Bhubaneswar")
    itc_res = next(s for s in results if s["site_name"] == "ITC Kohenur")

    # WH Bhubaneswar checks
    assert wh_res["status"] == "COMPLETED"
    assert wh_res["action_point_status"] == "ACTION POINT FOUND"
    assert wh_res["fetch_menu_status"] == "SUCCESS"
    assert wh_res["process_latest_menu_status"] == "SUCCESS"
    assert wh_res["download_status"] == "SUCCESS"

    # ITC Kohenur checks
    assert itc_res["status"] == "FAILED"
    assert itc_res["fetch_menu_status"] == "FAILED"
    assert itc_res["process_latest_menu_status"] == "BLOCKED"
    assert itc_res["download_status"] == "BLOCKED"
    assert itc_res["failure_code"] == "LAST_RECEIVED_DATE_NOT_CURRENT"

    print("[OK] Test 3: Successful and failed site stage results verified.")

    # TEST 4: Multiple runs ordered newest first (ORDER BY id DESC)
    print("\n[TEST 4] Verifying multiple runs ordered newest first...")
    run_2 = Run(
        run_date=today_str,
        start_time=datetime.now().strftime("%I:%M %p"),
        status="COMPLETED",
        total_sites=1,
        completed_sites=1,
        action_points_count=0,
        no_action_points_count=1,
        failed_sites_count=0
    )
    run_id_2 = create_run(run_2)

    history_all = get_runs_history(limit=50)
    assert history_all[0]["id"] == run_id_2, "Newest run should be first!"
    assert history_all[1]["id"] == run_id_1
    print("[OK] Test 4: Newest run first order verified.")

    print("\n======================================================================")
    print("ALL RUN HISTORY VERIFICATION TESTS PASSED SUCCESSFULLY!")
    print("======================================================================")

if __name__ == "__main__":
    test_run_history_today()
